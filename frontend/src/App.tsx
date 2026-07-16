import { Navigate, Route, Routes } from "react-router-dom";
import { TabBar } from "./components/TabBar";
import { StatusProvider } from "./StatusContext";
import Learn from "./pages/Learn";
import Review from "./pages/Review";
import Listen from "./pages/Listen";
import Speak from "./pages/Speak";
import Talk from "./pages/Talk";
import Me from "./pages/Me";

export default function App() {
  return (
    <StatusProvider>
      <div className="mx-auto flex min-h-screen max-w-xl flex-col">
        <main className="flex-1 pb-2">
          <Routes>
            <Route path="/" element={<Navigate to="/learn" replace />} />
            <Route path="/learn" element={<Learn />} />
            <Route path="/review" element={<Review />} />
            <Route path="/listen" element={<Listen />} />
            <Route path="/speak" element={<Speak />} />
            <Route path="/talk" element={<Talk />} />
            <Route path="/me" element={<Me />} />
            <Route path="*" element={<Navigate to="/learn" replace />} />
          </Routes>
        </main>
        <TabBar />
      </div>
    </StatusProvider>
  );
}
