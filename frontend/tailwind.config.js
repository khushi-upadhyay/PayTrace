/** @type {import('tailwindcss').Config} */
const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

// Every palette family reads its channels from CSS variables (app/palette.css),
// so palette changes happen in one place.
const themed = (name) =>
  Object.fromEntries(shades.map((s) => [s, `rgb(var(--${name}-${s}) / <alpha-value>)`]));

module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
        display: ["var(--font-display)", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
      },
      colors: {
        slate: themed("slate"),
        cyan: themed("cyan"), // PayPal blue scale
        amber: themed("amber"),
        emerald: themed("emerald"),
        rose: themed("rose"),
        sky: themed("sky"),
        purple: themed("purple"),
        indigo: themed("indigo"),
        // Headline text: PayPal navy-black.
        ink: "rgb(var(--ink) / <alpha-value>)",
        // Text on solid brand-coloured buttons.
        onsolid: "#ffffff",
        onamber: "#1c1300",
        paypal: {
          navy: "#1e2d8a",
          blue: "#2c4fae",
          sky: "#85cbf9",
          cream: "#f9f7f3",
        },
      },
      borderRadius: {
        lg: "0.5rem",
        xl: "0.75rem",
        "2xl": "0.75rem",
        md: "calc(0.5rem - 2px)",
        sm: "calc(0.5rem - 4px)",
      },
      keyframes: {
        fadeIn: { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
      },
      animation: { fadeIn: "fadeIn 0.3s ease-out both" },
    },
  },
  plugins: [],
};
