import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        soil: "#5a2a1a",
        field: "#7c9a3d",
        grain: "#f2c572",
        river: "#1f5c72",
        cloud: "#f7f2e8"
      }
    }
  },
  plugins: [typography]
};

export default config;
