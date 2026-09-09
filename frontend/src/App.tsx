import { Link, Outlet, RouterProvider, createBrowserRouter } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { Header } from "./components/Header";
import { ConversationPage } from "./pages/ConversationPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { HomePage } from "./pages/HomePage";
import { SavedListPage } from "./pages/SavedListPage";
import { SessionDetailPage } from "./pages/SessionDetailPage";
import { SignInPage } from "./pages/SignInPage";
import { SignUpPage } from "./pages/SignUpPage";

// Plan.md section 8 was amended in Sprint 3: captioning and guide mode are
// still one widget behind two tabs, and the pages added here are the ones
// that could not be a panel inside it -- what an account has kept, and one
// kept thing, which has to be somewhere a link can point at.
//
// A data router rather than <BrowserRouter>, because useBlocker only
// exists on this one, and stopping someone from navigating away from
// unsaved edits is the reason the detail page can be trusted.
function Shell() {
  return (
    <AuthProvider>
      <div className="widget">
        <Header />
        {/* A main landmark, so a screen reader can skip the header and
            get to the thing the page is for. It was lost in Sprint 3:
            <main className="widget"> became this div when the router
            shell took over, and nothing noticed until Sprint 6 looked. */}
        <main className="page-main">
          <Outlet />
        </main>
      </div>
    </AuthProvider>
  );
}

function NotFound() {
  return (
    <div className="page">
      <h1 className="page-title">That page does not exist.</h1>
      <Link className="account-link" to="/">
        Back to live captions
      </Link>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/signin", element: <SignInPage /> },
      { path: "/signup", element: <SignUpPage /> },
      { path: "/saved", element: <SavedListPage /> },
      { path: "/saved/:id", element: <SessionDetailPage /> },
      { path: "/conversations", element: <ConversationsPage /> },
      { path: "/conversations/:id", element: <ConversationPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
