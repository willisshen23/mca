/* ==========================================================================
   FAB 统一风格 —— React 基础组件（对应 BOHAI 项目）
   放到 BOHAI_Bank_Manager_Assistant-main/frontend/src/ui/index.tsx
   然后把页面里手写的 className 串换成这些组件，样式就自动统一了。
   依赖：react、lucide-react（BOHAI 已装），以及本套件的 tailwind.config.js
   ========================================================================== */
import type { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes,
              SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

const cx = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(' ');

/* ── 按钮 ──────────────────────────────────────────────────────────────── */
type BtnVariant = 'primary' | 'outline' | 'default' | 'text' | 'danger' | 'dangerGhost';
type BtnSize = 'sm' | 'md' | 'lg';

const BTN_BASE =
  'inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium ' +
  'border transition-colors duration-150 ease-out-soft ' +
  'disabled:bg-sunken disabled:border-line disabled:text-t4 disabled:cursor-not-allowed';

const BTN_VARIANT: Record<BtnVariant, string> = {
  primary:     'bg-primary border-primary text-white hover:bg-primary-hover hover:border-primary-hover active:bg-primary-active',
  outline:     'bg-white border-primary-border text-primary hover:bg-primary-weak hover:border-primary',
  default:     'bg-white border-line-strong text-t1 hover:bg-primary-weaker hover:border-line-hover hover:text-primary',
  text:        'bg-transparent border-transparent text-primary hover:bg-primary-weak px-2',
  danger:      'bg-danger border-danger text-white hover:bg-danger-hover hover:border-danger-hover',
  dangerGhost: 'bg-white border-danger-border text-danger hover:bg-danger-weak hover:border-danger',
};

const BTN_SIZE: Record<BtnSize, string> = {
  sm: 'h-ctl-sm px-3 text-xs',
  md: 'h-ctl px-4 text-sm',
  lg: 'h-ctl-lg px-6 text-base',
};

export function Button({
  variant = 'default', size = 'md', pill = false, block = false,
  icon, children, className, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant; size?: BtnSize; pill?: boolean; block?: boolean; icon?: ReactNode;
}) {
  return (
    <button
      className={cx(
        BTN_BASE, BTN_VARIANT[variant], BTN_SIZE[size],
        pill ? 'rounded-pill px-6' : 'rounded-md',
        block && 'w-full flex',
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}

export function IconButton({ size = 'md', className, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { size?: BtnSize; variant?: BtnVariant; icon?: ReactNode }) {
  const w = size === 'sm' ? 'w-ctl-sm' : size === 'lg' ? 'w-ctl-lg' : 'w-ctl';
  return <Button size={size} className={cx(w, 'px-0', className)} {...rest} />;
}

/* ── 表单 ──────────────────────────────────────────────────────────────── */
const FIELD_BASE =
  'w-full border border-line-strong rounded-sm bg-white text-sm text-t1 outline-none ' +
  'transition-colors duration-150 placeholder:text-t4 ' +
  'hover:border-line-hover focus:border-primary focus:shadow-focus ' +
  'disabled:bg-sunken disabled:text-t4 disabled:cursor-not-allowed';

export const Input = ({ className, error, ...rest }:
  InputHTMLAttributes<HTMLInputElement> & { error?: boolean }) => (
  <input className={cx(FIELD_BASE, 'h-ctl px-3', error && 'border-danger', className)} {...rest} />
);

export const Select = ({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cx(FIELD_BASE, 'h-ctl pl-3 pr-8 appearance-none bg-no-repeat', className)}
    style={{
      backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 4.5L6 8l3.5-3.5' fill='none' stroke='%23727472' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
      backgroundPosition: 'right 12px center',
    }}
    {...rest}>{children}</select>
);

export const Textarea = ({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cx(FIELD_BASE, 'min-h-[92px] px-3 py-2 leading-relaxed resize-y', className)} {...rest} />
);

export function Field({ label, required, help, error, children }: {
  label?: string; required?: boolean; help?: string; error?: string; children: ReactNode;
}) {
  return (
    <div className="mb-4">
      {label && (
        <label className="block mb-2 text-xs font-medium text-t2">
          {label}{required && <span className="text-danger"> *</span>}
        </label>
      )}
      {children}
      {(error || help) && (
        <div className={cx('mt-1 text-xs', error ? 'text-danger' : 'text-t3')}>{error || help}</div>
      )}
    </div>
  );
}

export function SearchBox({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={cx(
      'flex items-center gap-2 h-ctl px-3 bg-white border border-line-strong rounded-pill',
      'transition-colors focus-within:border-primary focus-within:shadow-focus', className)}>
      <svg className="w-4 h-4 shrink-0 text-t3" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
      </svg>
      <input className="flex-1 min-w-0 bg-transparent border-0 outline-none text-sm" {...rest} />
    </div>
  );
}

/* ── 卡片 ──────────────────────────────────────────────────────────────── */
export function Card({ title, subtitle, extra, footer, hoverable, className, children }: {
  title?: ReactNode; subtitle?: ReactNode; extra?: ReactNode; footer?: ReactNode;
  hoverable?: boolean; className?: string; children?: ReactNode;
}) {
  return (
    <div className={cx(
      'bg-white border border-line rounded-lg shadow-xs',
      hoverable && 'cursor-pointer transition-all duration-200 hover:border-primary-border hover:shadow-md hover:-translate-y-0.5',
      className)}>
      {(title || extra) && (
        <div className="flex items-center gap-3 px-5 py-4 border-b border-line-weak">
          <div>
            {title && <div className="text-h4">{title}</div>}
            {subtitle && <div className="text-xs text-t3">{subtitle}</div>}
          </div>
          {extra && <div className="ml-auto flex items-center gap-2">{extra}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
      {footer && <div className="flex justify-end gap-2 px-5 py-4 border-t border-line-weak">{footer}</div>}
    </div>
  );
}

export function Metric({ label, value, unit, trend, accent, icon }: {
  label: string; value: ReactNode; unit?: string; accent?: boolean; icon?: ReactNode;
  trend?: { dir: 'up' | 'down' | 'flat'; text: string };
}) {
  const trendCls = trend?.dir === 'up' ? 'text-success'
                 : trend?.dir === 'down' ? 'text-danger' : 'text-t3';
  return (
    <div className="bg-white border border-line rounded-lg shadow-xs p-5">
      <div className="flex items-center gap-2 text-xs text-t3">{icon}{label}</div>
      <div className={cx('mt-2 text-metric num', accent ? 'text-primary' : 'text-t1')}>
        {value}{unit && <span className="ml-1 text-xs font-normal text-t3">{unit}</span>}
      </div>
      {trend && <div className={cx('mt-2 text-xs flex items-center gap-1', trendCls)}>{trend.text}</div>}
    </div>
  );
}

/* ── 标签 / 状态 ───────────────────────────────────────────────────────── */
type TagTone = 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'violet';
const TAG_TONE: Record<TagTone, string> = {
  default: 'bg-sunken text-t2',
  primary: 'bg-primary-weak text-primary',
  success: 'bg-success-weak text-success',
  warning: 'bg-warning-weak text-warning',
  danger:  'bg-danger-weak text-danger',
  violet:  'bg-violet-weak text-[#5A5FD6]',
};
export const Tag = ({ tone = 'default', pill, children }:
  { tone?: TagTone; pill?: boolean; children: ReactNode }) => (
  <span className={cx('inline-flex items-center gap-1 px-2 py-0.5 text-2xs font-medium whitespace-nowrap',
    pill ? 'rounded-pill px-3' : 'rounded-sm', TAG_TONE[tone])}>{children}</span>
);

export const StatusDot = ({ tone = 'online', children }:
  { tone?: 'online' | 'busy' | 'offline'; children: ReactNode }) => {
  const c = { online: 'bg-success', busy: 'bg-warning', offline: 'bg-danger' }[tone];
  const ring = { online: 'ring-success-weak', busy: 'ring-warning-weak', offline: 'ring-danger-weak' }[tone];
  return (
    <span className="inline-flex items-center gap-2 text-xs text-t2">
      <span className={cx('w-[7px] h-[7px] rounded-full shrink-0 ring-[3px]', c, ring)} />
      {children}
    </span>
  );
};

/* ── 提示条 ────────────────────────────────────────────────────────────── */
type AlertTone = 'info' | 'success' | 'warning' | 'danger';
const ALERT_TONE: Record<AlertTone, string> = {
  info:    'bg-primary-weak border-primary-weak text-primary',
  success: 'bg-success-weak border-success-border text-success',
  warning: 'bg-warning-weak border-warning-border text-warning',
  danger:  'bg-danger-weak border-danger-border text-danger',
};
export const Alert = ({ tone = 'info', icon, children }:
  { tone?: AlertTone; icon?: ReactNode; children: ReactNode }) => (
  <div className={cx('flex items-start gap-2 px-4 py-3 border rounded-md text-xs leading-relaxed', ALERT_TONE[tone])}>
    {icon && <span className="shrink-0 mt-px">{icon}</span>}
    <span>{children}</span>
  </div>
);

/* ── 表格 ──────────────────────────────────────────────────────────────── */
export const TableWrap = ({ children, footer }: { children: ReactNode; footer?: ReactNode }) => (
  <div className="bg-white border border-line rounded-lg overflow-hidden">
    <div className="w-full overflow-x-auto">{children}</div>
    {footer && <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-line-weak text-xs text-t3">{footer}</div>}
  </div>
);
export const Table = ({ children, className }: { children: ReactNode; className?: string }) => (
  <table className={cx('w-full border-collapse', className)}>{children}</table>
);
export const Th = ({ children, num, className }: { children?: ReactNode; num?: boolean; className?: string }) => (
  <th className={cx('px-4 py-3 bg-subtle text-xs font-medium text-t3 whitespace-nowrap border-b border-line',
    num ? 'text-right num' : 'text-left', className)}>{children}</th>
);
export const Td = ({ children, num, primary, className }:
  { children?: ReactNode; num?: boolean; primary?: boolean; className?: string }) => (
  <td className={cx('px-4 py-3 text-sm border-b border-line-weak align-middle',
    num && 'text-right num', primary ? 'text-t1 font-medium' : 'text-t2', className)}>{children}</td>
);
export const Tr = ({ children, selected }: { children: ReactNode; selected?: boolean }) => (
  <tr className={cx('transition-colors', selected ? 'bg-primary-weak' : 'hover:bg-primary-weaker')}>{children}</tr>
);

/* ── 导航项 ────────────────────────────────────────────────────────────── */
export const NavLinkStyle = (active: boolean) => cx(
  'inline-flex items-center gap-2 h-ctl px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors',
  active ? 'bg-primary-weak text-primary' : 'text-t2 hover:bg-primary-weaker hover:text-primary',
);

export const Brand = ({ name, sub }: { name: string; sub?: string }) => (
  <div className="inline-flex items-center gap-3 shrink-0">
    <span className="w-8 h-8 rounded-md bg-brand text-white flex items-center justify-center text-xs font-bold tracking-wide">FAB</span>
    <span>
      <span className="block text-h4 tracking-wide">{name}</span>
      {sub && <span className="block text-2xs text-t3 tracking-wide">{sub}</span>}
    </span>
  </div>
);

/* ── 空状态 ────────────────────────────────────────────────────────────── */
export const Empty = ({ title, desc, icon, action }:
  { title: string; desc?: string; icon?: ReactNode; action?: ReactNode }) => (
  <div className="py-12 px-6 text-center">
    {icon && <div className="mx-auto mb-4 text-line-hover">{icon}</div>}
    <div className="text-base text-t2 mb-1">{title}</div>
    {desc && <div className="text-xs text-t3">{desc}</div>}
    {action && <div className="mt-5">{action}</div>}
  </div>
);
