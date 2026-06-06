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
        soil: "#1b4332",    // Forest green primary (replacing brown soil)
        field: "#2d6a4f",   // Accent green
        grain: "#38bdf8",   // Light blue (replacing yellow grain)
        river: "#0284c7",   // Slate/Light Blue secondary
        cloud: "#f0f9ff"    // Very light blue background tint (replacing cloud beige)
      }
    }
  },
  plugins: [typography]
};

export default config;
