/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        speaker: {
          1: "#3b82f6",
          2: "#f97316",
          3: "#10b981",
          4: "#a855f7",
          5: "#ef4444",
          6: "#eab308",
          7: "#06b6d4",
          8: "#ec4899",
        },
      },
    },
  },
  plugins: [],
};
