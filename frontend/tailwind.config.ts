import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: { DEFAULT: "#0f1115", light: "#ffffff" },
        panel: { DEFAULT: "#171a21", light: "#f4f5f7" },
        accent: { DEFAULT: "#3d8bff", dim: "#1c3a63" },
        danger: "#e5484d",
        warn: "#f2a33c",
        ok: "#33b06f",
      },
      borderRadius: { xl: "0.9rem" },
    },
  },
  plugins: [],
};
export default config;
