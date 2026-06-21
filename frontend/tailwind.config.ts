import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "ui-sans-serif", "system-ui"]
      },
      colors: {
        ink: "#1f2933",
        mist: "#eef3f1",
        clay: "#9b6b5e",
        moss: "#607466",
        tide: "#4f6f7a",
        amberSoft: "#d9a441"
      },
      boxShadow: {
        calm: "0 18px 60px rgba(31, 41, 51, 0.10)"
      }
    }
  },
  plugins: []
};

export default config;

