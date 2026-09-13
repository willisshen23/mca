/** ==========================================================================
 *  FAB 统一风格 —— Tailwind 主题映射（对应 BOHAI 项目）
 *  --------------------------------------------------------------------------
 *  用法：把本文件覆盖 BOHAI_Bank_Manager_Assistant-main/frontend/tailwind.config.js
 *  原文件 theme.extend 是空的，所有颜色都在用 Tailwind 默认调色板；
 *  覆盖后 `bg-primary` / `text-t2` / `rounded-lg` / `shadow-sm` 等类
 *  直接对应统一 token，不必再写 blue-600 / gray-500 这类原生色。
 *
 *  注意：本文件的取值与 tokens/design-tokens.css、tokens/tokens.json 保持一致，
 *  改动请三处同步（或直接用 var() 引用 CSS 变量，见下方 cssVar 写法）。
 *  ========================================================================== */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: '#0081E4',
          cyan: '#02A6C9',
          deep: '#1E57AE',
        },
        primary: {
          DEFAULT: '#2B6EDD',
          hover:   '#1F5BC4',
          active:  '#17499F',
          weak:    '#EAF1FD',
          weaker:  '#F5F9FE',
          border:  '#BFD5F6',
        },
        violet: { DEFAULT: '#8D9DF8', weak: '#EFF0FE' },
        success: { DEFAULT: '#12A150', weak: '#E8F7EE', border: '#A8E0C2' },
        warning: { DEFAULT: '#E08700', weak: '#FDF3E2', border: '#F2D19A' },
        danger:  { DEFAULT: '#D92B2B', hover: '#B81F1F', weak: '#FDECEC', border: '#F2B5B5' },

        // 文字（用法：text-t1 / text-t2 / text-t3 / text-t4）
        t1: '#191919',
        t2: '#4A4F58',
        t3: '#727472',
        t4: '#A3A8AF',

        // 背景（用法：bg-page / bg-subtle / bg-sunken）
        page:   '#FFFFFF',
        subtle: '#F6F9FD',
        sunken: '#EDF3FB',

        // 描边（用法：border-line / border-line-strong）
        line: {
          DEFAULT: '#E5EFF9',
          weak:    '#EEF3FA',
          strong:  '#D6E1F3',
          hover:   '#BFD5F6',
        },
      },

      backgroundImage: {
        'hero':        'linear-gradient(180deg, #A4C7F0 0%, #C4DBF8 46%, #F2F6FB 88%, #FFFFFF 100%)',
        'hero-violet': 'radial-gradient(78% 120% at 92% 2%, rgba(141,157,248,.78) 0%, rgba(141,157,248,.28) 38%, rgba(141,157,248,0) 66%)',
        'brand':       'linear-gradient(135deg, #0081E4 0%, #2B6EDD 55%, #8D9DF8 100%)',
        'brand-soft':  'linear-gradient(135deg, #EAF1FD 0%, #EFF0FE 100%)',
        'sidebar':     'linear-gradient(180deg, #17499F 0%, #1F5BC4 58%, #2B6EDD 100%)',
      },

      fontFamily: {
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI',
               'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
               'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },

      // 只保留统一字阶这 10 档。禁止再写 text-[10px] 这类任意值。
      fontSize: {
        '2xs':     ['11px', { lineHeight: '1.45' }],
        'xs':      ['12px', { lineHeight: '1.5'  }],
        'sm':      ['13px', { lineHeight: '1.55' }],
        'base':    ['14px', { lineHeight: '1.6'  }],   // 基准
        'h4':      ['16px', { lineHeight: '1.5',  fontWeight: '600' }],
        'h3':      ['18px', { lineHeight: '1.45', fontWeight: '600' }],
        'h2':      ['22px', { lineHeight: '1.4',  fontWeight: '600' }],
        'h1':      ['28px', { lineHeight: '1.35', fontWeight: '600' }],
        'display': ['40px', { lineHeight: '1.25', fontWeight: '700' }],
        'metric':  ['32px', { lineHeight: '1.2',  fontWeight: '600' }],
      },

      borderRadius: {
        xs:   '4px',
        sm:   '6px',
        md:   '10px',
        lg:   '14px',   // 卡片
        xl:   '20px',   // 弹窗
        '2xl':'28px',
        pill: '999px',
      },

      boxShadow: {
        xs:    '0 1px 2px rgba(30, 58, 110, .05)',
        sm:    '0 2px 8px rgba(30, 58, 110, .06)',
        md:    '0 6px 20px rgba(30, 58, 110, .08)',
        lg:    '0 14px 40px rgba(30, 58, 110, .12)',
        focus: '0 0 0 3px rgba(43, 110, 221, .16)',
      },

      height:   { 'ctl-sm': '28px', 'ctl': '34px', 'ctl-lg': '42px', 'topbar': '64px' },
      minHeight:{ 'ctl': '34px' },
      maxWidth: { 'content': '1920px' },
      spacing:  { 'gutter': '24px' },

      transitionTimingFunction: { 'out-soft': 'cubic-bezier(.22,.61,.36,1)' },

      keyframes: {
        fadeUp: { '0%': { opacity: '0', transform: 'translateY(6px)' },
                  '100%': { opacity: '1', transform: 'none' } },
      },
      animation: { fadeUp: 'fadeUp .32s cubic-bezier(.22,.61,.36,1) both' },
    },
  },
  plugins: [],
}
