/**
 * The seeded accounts offered on the sign-in screen.
 *
 * A plain module, not part of login/actions.ts, because a `"use server"` file
 * may only export async functions — a const object there is a build error.
 *
 * The demo buttons submit these as real credentials through `signIn`, so they
 * go through the same scrypt check as anything typed by hand. A one-click
 * bypass that minted a session directly would reopen exactly the hole that
 * signing the session cookie closed.
 */
export const DEMO_ACCOUNTS = {
  student: {
    email: "achol.majok@student.example.ss",
    label: "Achol Majok — continuing student",
  },
  alumni: {
    email: "nyandeng.chol@student.example.ss",
    label: "Nyandeng Chol — alumna (graduated)",
  },
  applicant: {
    email: "emmanuel.wani@example.ss",
    label: "Emmanuel Wani — applicant",
  },
  admin: {
    email: "grace.lueth@uoj.example.ss",
    label: "Grace Lueth — super administrator",
  },
  registrar: {
    email: "daniel.kuek@uoj.example.ss",
    label: "Daniel Kuek — Registrar",
  },
  lecturer: {
    email: "peter.lado@uoj.example.ss",
    label: "Dr. Peter Lado — Lecturer",
  },
  head_of_department: {
    email: "achol.mayen@uoj.example.ss",
    label: "Dr. Achol Mayen — Head of department",
  },
  bursar: {
    email: "aluel.deng@uoj.example.ss",
    label: "Aluel Deng — Bursar",
  },
  it_support: {
    email: "peter.deng@uoj.example.ss",
    label: "Peter Deng — IT support",
  },
} as const;

export type DemoAccountKey = keyof typeof DEMO_ACCOUNTS;

/** The password every seeded account shares — see the note in store.ts. */
export const DEMO_PASSWORD = "portal123";
