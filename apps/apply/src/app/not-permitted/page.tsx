import { NotPermitted } from "@acmis/ui/components/empty-state"

export const metadata = { title: "Not permitted" }

export default function NotPermittedPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <NotPermitted what="this part of the system" />
    </div>
  )
}
