/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fffbeb",
          100: "#fef3c7",
          200: "#fde68a",
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
          700: "#b45309",
          800: "#92400e",
          900: "#78350f",
          950: "#451a03",
        },
        accent: {
          50: "#ecfdf5",
          100: "#d1fae5",
          200: "#a7f3d0",
          400: "#34d399",
          500: "#10b981",
          600: "#059669",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
          950: "#022c22",
        },
        surface: {
          DEFAULT: "var(--pic-surface)",
          raised: "var(--pic-surface-raised)",
          muted: "var(--pic-surface-muted)",
          inset: "var(--pic-surface-inset)",
          chrome: "var(--pic-surface-chrome)",
          light: "#f7f5f2",
          dark: "#0c0a09",
        },
      },
      borderRadius: {
        pic: "var(--pic-radius-md)",
        "pic-sm": "var(--pic-radius-sm)",
        "pic-lg": "var(--pic-radius-lg)",
        "pic-xl": "var(--pic-radius-xl)",
      },
      spacing: {
        "pic-1": "var(--pic-space-1)",
        "pic-2": "var(--pic-space-2)",
        "pic-3": "var(--pic-space-3)",
        "pic-4": "var(--pic-space-4)",
        "pic-5": "var(--pic-space-5)",
        "pic-6": "var(--pic-space-6)",
      },
      boxShadow: {
        pic: "var(--pic-shadow-sm)",
        "pic-md": "var(--pic-shadow-md)",
      },
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        display: ["Outfit", "DM Sans", "system-ui", "sans-serif"],
      },
      fontSize: {
        "pic-xs": ["var(--pic-text-xs)", { lineHeight: "var(--pic-leading-snug)" }],
        "pic-sm": ["var(--pic-text-sm)", { lineHeight: "var(--pic-leading-snug)" }],
        "pic-base": ["var(--pic-text-base)", { lineHeight: "var(--pic-leading-normal)" }],
        "pic-lg": ["var(--pic-text-lg)", { lineHeight: "var(--pic-leading-tight)" }],
        "pic-xl": ["var(--pic-text-xl)", { lineHeight: "var(--pic-leading-tight)" }],
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-out forwards",
        "slide-up": "slideUp 0.45s ease-out forwards",
        float: "float 6s ease-in-out infinite",
        shimmer: "shimmer 2.5s linear infinite",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(12px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        float: { "0%, 100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-8px)" } },
        shimmer: { "0%": { backgroundPosition: "200% 0" }, "100%": { backgroundPosition: "-200% 0" } },
      },
      backgroundImage: {
        "hero-gradient":
          "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(245,158,11,0.18), transparent), radial-gradient(ellipse 50% 40% at 90% 20%, rgba(16,185,129,0.12), transparent)",
        "hero-gradient-dark":
          "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(245,158,11,0.12), transparent), radial-gradient(ellipse 50% 40% at 90% 20%, rgba(16,185,129,0.08), transparent)",
      },
    },
  },
  plugins: [],
};
