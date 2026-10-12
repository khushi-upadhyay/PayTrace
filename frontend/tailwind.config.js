/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(215 27.9% 16.9%)",
        background: "hsl(222 47% 7%)",
        foreground: "hsl(210 40% 98%)",
        card: {
          DEFAULT: "hsl(222 47% 9%)",
          foreground: "hsl(210 40% 98%)",
        },
        primary: {
          DEFAULT: "hsl(199 89% 48%)", // PayPal/Cyber Cyan
          foreground: "hsl(210 40% 98%)",
        },
        secondary: {
          DEFAULT: "hsl(217 32% 17%)",
          foreground: "hsl(210 40% 98%)",
        },
        muted: {
          DEFAULT: "hsl(217 32% 14%)",
          foreground: "hsl(215 20.2% 65.1%)",
        },
        accent: {
          DEFAULT: "hsl(217 32% 20%)",
          foreground: "hsl(210 40% 98%)",
        },
        destructive: {
          DEFAULT: "hsl(0 84.2% 60.2%)",
          foreground: "hsl(210 40% 98%)",
        },
        warning: {
          DEFAULT: "hsl(38 92% 50%)",
          foreground: "hsl(210 40% 98%)",
        },
        success: {
          DEFAULT: "hsl(142 76% 45%)",
          foreground: "hsl(210 40% 98%)",
        },
      },
      borderRadius: {
        lg: "0.5rem",
        md: "calc(0.5rem - 2px)",
        sm: "calc(0.5rem - 4px)",
      },
    },
  },
  plugins: [],
}
