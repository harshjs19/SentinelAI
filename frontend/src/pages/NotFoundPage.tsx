import { Link } from "react-router-dom";
import { EmptyState } from "../components/States";

export function NotFoundPage() {
  return <EmptyState title="Workspace route not found" message="The requested dashboard view does not exist." action={<Link className="button button--primary" to="/">Return to overview</Link>} />;
}
