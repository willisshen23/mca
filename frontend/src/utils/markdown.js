// 零依赖 Markdown 渲染器（聊天消息专用）。
//
// 设计决策：
// - 不引入 marked/markdown-it + DOMPurify —— 行内为离线部署环境，新增 npm
//   依赖需要同步离线 registry，成本高。本实现覆盖智能体回复实际使用的语法。
// - 安全模型：先对全文做 HTML 实体转义（模型输出中的任何原始 HTML/脚本
//   全部惰性化），再在其上应用 Markdown 语法转换，因此无需单独的 sanitizer。
//
// 支持语法：标题(#~####)、粗体/斜体/行内代码、代码块、无序/有序列表、
// GFM 表格、引用块、链接 [text](http/https)、单换行转 <br>。

const HTML_ESCAPE = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
};

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => HTML_ESCAPE[ch]);
}

function renderInline(text) {
  let out = text;
  // 行内代码
  out = out.replace(/`([^`\n]+)`/g, (_m, code) => `<code>${code}</code>`);
  // 粗体（先于斜体处理）
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // 斜体
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  // 链接（仅允许 http/https，防止 javascript: 协议注入）
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return out;
}

function isTableSeparator(line) {
  return /^\|?[\s:|-]+\|[\s:|-]*$/.test(line.trim()) && line.includes('-');
}

function splitTableRow(line) {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map((cell) => cell.trim());
}

function renderTable(lines, selectedRowNumbers = new Set(), transformTableCell = null) {
  const headers = splitTableRow(lines[0]);
  const rows = lines.slice(2).map(splitTableRow);
  const isSelectable = headers[0]?.replace(/<[^>]+>|[*_]/g, '').trim() === '序号';
  let html = '<table><thead><tr>';
  for (const h of headers) html += `<th>${renderInline(h)}</th>`;
  html += '</tr></thead><tbody>';
  for (const [rowIndex, row] of rows.entries()) {
    const rowNumber = Number.parseInt(row[0], 10);
    const selectableClass = isSelectable && Number.isInteger(rowNumber)
      ? ` class="is-selectable${selectedRowNumbers.has(rowNumber) ? ' is-selected' : ''}" data-row-number="${rowNumber}"`
      : '';
    html += `<tr${selectableClass}>`;
    for (const [columnIndex, cell] of row.entries()) {
      const displayCell = typeof transformTableCell === 'function'
        ? transformTableCell(cell, { headers, row, rowIndex, columnIndex })
        : cell;
      html += `<td>${renderInline(displayCell ?? cell)}</td>`;
    }
    html += '</tr>';
  }
  return html + '</tbody></table>';
}

export function renderMarkdown(text, options = {}) {
  const source = String(text ?? '');
  if (!source.trim()) return '';
  const selectedRowNumbers = new Set(options.selectedRowNumbers || []);
  const transformTableCell = options.transformTableCell;
  const transformText = options.transformText;

  // 1. 提取代码块为占位符，避免内部内容被其他规则处理
  const codeBlocks = [];
  let work = source.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _lang, code) => {
    codeBlocks.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`);
    return `@@CODEBLOCK_${codeBlocks.length - 1}@@`;
  });

  if (typeof transformText === 'function') {
    work = transformText(work);
  }

  // 2. 全文 HTML 转义（此后的转换只产出受控标签）
  work = escapeHtml(work);

  const lines = work.split('\n');
  const html = [];
  let i = 0;
  let paragraph = [];

  function flushParagraph() {
    if (paragraph.length) {
      html.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`);
      paragraph = [];
    }
  }

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // 代码块占位符（整行）
    const placeholder = trimmed.match(/^@@CODEBLOCK_(\d+)@@$/);
    if (placeholder && codeBlocks[Number(placeholder[1])] !== undefined) {
      flushParagraph();
      html.push(codeBlocks[Number(placeholder[1])]);
      i += 1;
      continue;
    }

    // 空行 → 段落分隔
    if (!trimmed) {
      flushParagraph();
      i += 1;
      continue;
    }

    // 表格：当前行含 | 且下一行是分隔行
    if (trimmed.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      flushParagraph();
      const tableLines = [line, lines[i + 1]];
      i += 2;
      while (i < lines.length && lines[i].trim().includes('|') && lines[i].trim()) {
        tableLines.push(lines[i]);
        i += 1;
      }
      html.push(renderTable(tableLines, selectedRowNumbers, transformTableCell));
      continue;
    }

    // 标题
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    // 引用块
    if (trimmed.startsWith('&gt;') || trimmed.startsWith('>')) {
      flushParagraph();
      const quoteLines = [];
      while (i < lines.length && /^\s*(&gt;|>)/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*(&gt;|>)\s?/, ''));
        i += 1;
      }
      html.push(`<blockquote>${quoteLines.map(renderInline).join('<br>')}</blockquote>`);
      continue;
    }

    // 无序列表
    if (/^[-*•]\s+/.test(trimmed)) {
      flushParagraph();
      const items = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ''));
        i += 1;
      }
      html.push(`<ul>${items.map((item) => `<li>${renderInline(item)}</li>`).join('')}</ul>`);
      continue;
    }

    // 有序列表
    if (/^\d+[.、)]\s+/.test(trimmed)) {
      flushParagraph();
      const items = [];
      while (i < lines.length && /^\d+[.、)]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+[.、)]\s+/, ''));
        i += 1;
      }
      html.push(`<ol>${items.map((item) => `<li>${renderInline(item)}</li>`).join('')}</ol>`);
      continue;
    }

    // 普通文本行 → 累积进段落
    paragraph.push(line);
    i += 1;
  }
  flushParagraph();

  return html.join('\n');
}
