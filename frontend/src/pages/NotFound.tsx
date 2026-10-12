import { Link } from "react-router-dom";
import { EmptyState } from "@/components/ui/feedback";

export default function NotFound() {
  return (
    <EmptyState title="We couldn't find that page" action={<Link to="/" className="font-medium text-primary hover:underline">Back to today</Link>}>
      The link may be old, or the item may have been deleted.
    </EmptyState>
  );
}
