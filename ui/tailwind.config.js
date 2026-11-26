/** @type {import('tailwindcss').Config} */
const color = (name) => `rgb(var(--cl-${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'cl-bg': color('bg'),
        'cl-surface': color('surface'),
        'cl-raised': color('raised'),
        'cl-border': color('border'),
        'cl-text': color('text'),
        'cl-muted': color('muted'),
        'cl-accent': color('accent'),
        'cl-accent-text': color('accent-text'),
        'cl-on-accent': color('on-accent'),
        'cl-warning': color('warning'),
        'cl-danger': color('danger'),
      },
    },
  },
  plugins: [],
}
