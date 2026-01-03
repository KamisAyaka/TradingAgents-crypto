/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        heading: ['"Space Grotesk"', 'sans-serif'],
        body: ['"DM Sans"', 'sans-serif'],
      },
      colors: {
        background: '#0F172A', // Slate 900
        surface: '#1E293B',    // Slate 800
        primary: {
          DEFAULT: '#3B82F6', // Blue 500
          foreground: '#FFFFFF',
        },
        accent: {
          DEFAULT: '#F59E0B', // Amber 500
          foreground: '#FFFFFF',
        },
        success: '#26A69A', // Teal 400
        danger: '#EF5350',  // Red 400
      },
    },
  },
  plugins: [],
}
