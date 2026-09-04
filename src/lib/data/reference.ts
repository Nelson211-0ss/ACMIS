import type { Faculty, Programme } from "../types";

/** The ten states plus the three administrative areas. */
export const STATES = [
  "Central Equatoria",
  "Eastern Equatoria",
  "Western Equatoria",
  "Jonglei",
  "Lakes",
  "Northern Bahr el Ghazal",
  "Unity",
  "Upper Nile",
  "Warrap",
  "Western Bahr el Ghazal",
  "Abyei Administrative Area",
  "Ruweng Administrative Area",
  "Greater Pibor Administrative Area",
] as const;

/** Subjects examinable at the South Sudan Certificate of Secondary Education. */
export const SSCSE_SUBJECTS = [
  "English",
  "Mathematics",
  "Additional Mathematics",
  "Biology",
  "Chemistry",
  "Physics",
  "Geography",
  "History",
  "Agriculture",
  "Commerce",
  "Business Studies",
  "Computer Studies",
  "Christian Religious Education",
  "Islamic Religious Education",
  "Arabic",
  "Kiswahili",
  "Citizenship",
] as const;

export const FACULTIES: Faculty[] = [
  { id: "fac-med", name: "Medicine and Health Sciences", code: "MED" },
  { id: "fac-eng", name: "Engineering and Architecture", code: "ENG" },
  { id: "fac-sci", name: "Natural Sciences", code: "SCI" },
  { id: "fac-agr", name: "Agriculture and Environmental Studies", code: "AGR" },
  { id: "fac-edu", name: "Education", code: "EDU" },
  { id: "fac-law", name: "Law", code: "LAW" },
  { id: "fac-eco", name: "Economics and Social Studies", code: "ECO" },
];

export const PROGRAMMES: Programme[] = [
  {
    id: "prog-mbbs",
    facultyId: "fac-med",
    name: "Medicine and Surgery",
    code: "MBBS",
    durationYears: 6,
    award: "Bachelor",
    minimumAggregate: 80,
    intake: 60,
    tuitionPerSemesterSSP: 480_000,
    requiredSubjects: ["Biology", "Chemistry", "Physics", "English"],
  },
  {
    id: "prog-nur",
    facultyId: "fac-med",
    name: "Nursing Science",
    code: "BNS",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 65,
    intake: 90,
    tuitionPerSemesterSSP: 280_000,
    requiredSubjects: ["Biology", "Chemistry", "English"],
  },
  {
    id: "prog-pub",
    facultyId: "fac-med",
    name: "Public Health",
    code: "BPH",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 60,
    intake: 100,
    tuitionPerSemesterSSP: 240_000,
    requiredSubjects: ["Biology", "English"],
  },
  {
    id: "prog-civ",
    facultyId: "fac-eng",
    name: "Civil Engineering",
    code: "BCE",
    durationYears: 5,
    award: "Bachelor",
    minimumAggregate: 70,
    intake: 75,
    tuitionPerSemesterSSP: 320_000,
    requiredSubjects: ["Mathematics", "Physics", "English"],
  },
  {
    id: "prog-eee",
    facultyId: "fac-eng",
    name: "Electrical and Electronic Engineering",
    code: "BEE",
    durationYears: 5,
    award: "Bachelor",
    minimumAggregate: 70,
    intake: 60,
    tuitionPerSemesterSSP: 320_000,
    requiredSubjects: ["Mathematics", "Physics", "English"],
  },
  {
    id: "prog-csc",
    facultyId: "fac-sci",
    name: "Computer Science",
    code: "BCS",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 65,
    intake: 120,
    tuitionPerSemesterSSP: 260_000,
    requiredSubjects: ["Mathematics", "English"],
  },
  {
    id: "prog-sta",
    facultyId: "fac-sci",
    name: "Statistics and Data Science",
    code: "BST",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 60,
    intake: 80,
    tuitionPerSemesterSSP: 220_000,
    requiredSubjects: ["Mathematics", "English"],
  },
  {
    id: "prog-agr",
    facultyId: "fac-agr",
    name: "Agricultural Sciences",
    code: "BAG",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 55,
    intake: 150,
    tuitionPerSemesterSSP: 180_000,
    requiredSubjects: ["Biology", "English"],
  },
  {
    id: "prog-vet",
    facultyId: "fac-agr",
    name: "Veterinary Medicine",
    code: "BVM",
    durationYears: 5,
    award: "Bachelor",
    minimumAggregate: 70,
    intake: 45,
    tuitionPerSemesterSSP: 300_000,
    requiredSubjects: ["Biology", "Chemistry", "English"],
  },
  {
    id: "prog-edu-eng",
    facultyId: "fac-edu",
    name: "Education — English Language",
    code: "BED-E",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 50,
    intake: 200,
    tuitionPerSemesterSSP: 140_000,
    requiredSubjects: ["English"],
  },
  {
    id: "prog-edu-math",
    facultyId: "fac-edu",
    name: "Education — Mathematics",
    code: "BED-M",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 55,
    intake: 160,
    tuitionPerSemesterSSP: 140_000,
    requiredSubjects: ["Mathematics", "English"],
  },
  {
    id: "prog-law",
    facultyId: "fac-law",
    name: "Laws",
    code: "LLB",
    durationYears: 5,
    award: "Bachelor",
    minimumAggregate: 65,
    intake: 100,
    tuitionPerSemesterSSP: 260_000,
    requiredSubjects: ["English", "History"],
  },
  {
    id: "prog-eco",
    facultyId: "fac-eco",
    name: "Economics",
    code: "BEC",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 60,
    intake: 140,
    tuitionPerSemesterSSP: 200_000,
    requiredSubjects: ["Mathematics", "English"],
  },
  {
    id: "prog-ba",
    facultyId: "fac-eco",
    name: "Business Administration",
    code: "BBA",
    durationYears: 4,
    award: "Bachelor",
    minimumAggregate: 55,
    intake: 180,
    tuitionPerSemesterSSP: 200_000,
    requiredSubjects: ["Mathematics", "English"],
  },
];

export function facultyById(id: string): Faculty | undefined {
  return FACULTIES.find((f) => f.id === id);
}

export function programmeById(id: string): Programme | undefined {
  return PROGRAMMES.find((p) => p.id === id);
}

/** Programmes grouped under their faculty, for the choice picker. */
export function programmesByFaculty(): Array<{
  faculty: Faculty;
  programmes: Programme[];
}> {
  return FACULTIES.map((faculty) => ({
    faculty,
    programmes: PROGRAMMES.filter((p) => p.facultyId === faculty.id),
  })).filter((g) => g.programmes.length > 0);
}

/** Rough competitiveness signal, derived from intake size. */
export function competitiveness(p: Programme): "high" | "moderate" | "open" {
  if (p.intake <= 60 || p.minimumAggregate >= 75) return "high";
  if (p.intake <= 120) return "moderate";
  return "open";
}
