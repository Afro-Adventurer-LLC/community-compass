import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#0b1f33",
          700: "#16324d",
          500: "#2b4c6f",
        },
        accent: {
          DEFAULT: "#e47911",
          600: "#c8670c",
        },
      },
    },
  },
  plugins: [],
};

export default config;
