import type { ApplicationStatus } from "@acmis/api-client"
import type { StatusTone } from "@acmis/ui/components/status-badge"

/**
 * What a status means to the person it is about.
 *
 * Everywhere else in ACMIS a status is a word on a badge, read by somebody who
 * was trained on what it means. Here it is read by an applicant, once, and
 * "recommended" or "incomplete" on its own is either meaningless or
 * frightening. Each one therefore carries two things the staff screens do not
 * need: what it means, and whose move it is next.
 *
 * `waiting` is the field that earns its place. An applicant staring at
 * "under review" wants to know one thing — is there something I should be
 * doing? — and the honest answer is usually no. Saying so stops the phone
 * calls that a silent screen generates.
 */
export interface StatusMeaning {
  label: string
  tone: StatusTone
  /** One sentence: what this state is. */
  meaning: string
  /** What happens next, and who does it. */
  next: string
  /** True when the applicant has something to do. */
  yours: boolean
}

const MEANINGS: Record<ApplicationStatus, StatusMeaning> = {
  draft: {
    label: "Not sent yet",
    tone: "neutral",
    meaning: "You have started this application but not submitted it.",
    next: "Finish it and submit — nobody at the institution can see it until you do.",
    yours: true,
  },
  awaiting_fee: {
    label: "Fee not received",
    tone: "warning",
    meaning: "Your application is submitted, but the application fee has not reached us.",
    next: "Pay the fee using the details on your application. Review begins once it clears.",
    yours: true,
  },
  incomplete: {
    label: "Something is missing",
    tone: "warning",
    meaning: "The admissions office looked at your application and needs more from you.",
    next: "Open it to see what is missing, then send the missing piece.",
    yours: true,
  },
  submitted: {
    label: "Received",
    tone: "info",
    meaning: "We have your application. It is queued for the admissions office.",
    next: "Nothing from you for now. You will be told when it moves.",
    yours: false,
  },
  under_review: {
    label: "Being considered",
    tone: "info",
    meaning: "A selector is reading your application against the programmes you chose.",
    next: "Nothing from you. This is the longest stage, and silence here is normal.",
    yours: false,
  },
  interview: {
    label: "Interview",
    tone: "info",
    meaning: "Your programme requires an interview and you have reached that stage.",
    next: "Watch for the time and place — it comes by email and text.",
    yours: true,
  },
  recommended: {
    label: "Recommended",
    tone: "success",
    meaning: "The faculty has put your name forward. It is not an offer yet.",
    next: "The admissions board has to approve the list before offers go out.",
    yours: false,
  },
  admitted: {
    label: "Offer made",
    tone: "success",
    meaning: "You have been offered a place.",
    next: "Accept or decline before the acceptance deadline, or the place is released.",
    yours: true,
  },
  waitlisted: {
    label: "On the waiting list",
    tone: "warning",
    meaning: "You were not admitted outright, but you are in line if places free up.",
    next: "Nothing from you. Keep an eye on other applications in the meantime.",
    yours: false,
  },
  rejected: {
    label: "Not successful",
    tone: "danger",
    meaning: "This application was not successful.",
    next: "You can apply again in a future cycle. The reason, where one was given, is below.",
    yours: false,
  },
  offer_accepted: {
    label: "Place accepted",
    tone: "success",
    meaning: "You accepted the offer. Your place is held.",
    next: "Enrolment details follow from the registry before the semester starts.",
    yours: false,
  },
  enrolled: {
    label: "Enrolled",
    tone: "success",
    meaning: "You have taken up your place and are now a registered student.",
    next: "Use the student portal from here — this application is finished with.",
    yours: false,
  },
  withdrawn: {
    label: "Withdrawn",
    tone: "neutral",
    meaning: "This application was withdrawn.",
    next: "Nothing further happens on it. You may start a new one while the cycle is open.",
    yours: false,
  },
  offer_declined: {
    label: "Offer declined",
    tone: "neutral",
    meaning: "You turned this offer down.",
    next: "Nothing further happens on this application.",
    yours: false,
  },
}

export function meaningOf(status: ApplicationStatus): StatusMeaning {
  return (
    MEANINGS[status] ?? {
      label: status.replace(/_/g, " "),
      tone: "neutral" as StatusTone,
      meaning: "This application is at a stage this page does not recognise.",
      next: "Ask the admissions office where it stands.",
      yours: false,
    }
  )
}
