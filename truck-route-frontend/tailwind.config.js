/** @type {import('tailwindcss').Config} */
export default {
  theme: {
    extend: {
      colors: {
        brand: {
          midnight: "#02070A",
          panel: "#0B1218",
          blue: "#0297DE",
          cantaloupe: "#FC734D",
          priority: "#FC794D",
        },
      },
      boxShadow: {
        "blue-glow": "0 0 0 1px rgba(2,151,222,.45), 0 16px 44px rgba(2,151,222,.14)",
        "orange-glow": "0 0 24px rgba(252,115,77,.22)",
      },
    },
  },
};
