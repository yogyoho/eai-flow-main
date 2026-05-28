import { Outlet, createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/procurement')({
  component: ProcurementLayout,
})

function ProcurementLayout() {
  return <Outlet />
}
