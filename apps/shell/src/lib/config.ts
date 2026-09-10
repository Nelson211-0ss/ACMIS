import type { AppConfig } from "@acmis/auth/server"

/** This app's identity, sent on every API call and recorded in the audit trail. */
export const APP: AppConfig = { module: "shell", loginPath: "/sign-in" }
export const MODULE_KEY = "shell"
export const MODULE_NAME = "ACMIS"
