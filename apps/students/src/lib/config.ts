import type { AppConfig } from "@acmis/auth/server"

/** This app's identity, sent on every API call and recorded in the audit trail. */
export const APP: AppConfig = { module: "students", loginPath: "/sign-in" }
export const MODULE_KEY = "students"
export const MODULE_NAME = "Student Records"
