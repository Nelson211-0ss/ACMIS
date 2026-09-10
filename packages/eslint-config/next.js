import pluginNext from "@next/eslint-plugin-next"
import { config as reactConfig } from "./react-library.js"

export const config = [
  ...reactConfig,
  {
    plugins: { "@next/next": pluginNext },
    rules: {
      ...pluginNext.configs.recommended.rules,
      ...pluginNext.configs["core-web-vitals"].rules,
    },
  },
]

export default config
