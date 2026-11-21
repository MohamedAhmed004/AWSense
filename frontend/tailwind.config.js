/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0E1520', panel: '#142030', raised: '#1B2A3E', line: '#26374D',
        text: '#E5EBF3', muted: '#8B9BB0', accent: '#5AA9FF',
        crit: '#F0645A', high: '#F29A4B', med: '#E3C453', low: '#4FBF9F',
      },
      fontFamily: { sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
}
