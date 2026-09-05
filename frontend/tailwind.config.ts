import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bull: "#16a34a",
        bear: "#dc2626",
        doji: "#7c3aed",
      },
    },
  },
  plugins: [],
};

export default config;
