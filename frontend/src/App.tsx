import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { TabBar } from "./components/TabBar";
import { StatusProvider } from "./StatusContext";
import { SettingsProvider } from "./SettingsContext";
import Learn from "./pages/Learn";
import LessonPlayer from "./pages/learn/LessonPlayer";
import Review from "./pages/Review";
import Listen from "./pages/Listen";
import Speak from "./pages/Speak";
import Talk from "./pages/Talk";
import Me from "./pages/Me";

export default function App() {
  // Hide the tab bar during a lesson so the exercise gets the full screen.
  const location = useLocation();
  const inLesson = /^\/learn\/.+/.test(location.pathname);

  return (
    <StatusProvider>
      <SettingsProvider>
        <div className="mx-auto flex min-h-screen max-w-xl flex-col">
          <main className="flex-1 pb-2">
            <Routes>
              <Route path="/" element={<Navigate to="/learn" replace />} />
              <Route path="/learn" element={<Learn />} />
              <Route path="/learn/:lessonId" element={<LessonPlayer />} />
              <Route path="/review" element={<Review />} />
              <Route path="/listen" element={<Listen />} />
              <Route path="/speak" element={<Speak />} />
              <Route path="/talk" element={<Talk />} />
              <Route path="/me" element={<Me />} />
              <Route path="*" element={<Navigate to="/learn" replace />} />
            </Routes>
          </main>
          {!inLesson && <TabBar />}
        </div>
      </SettingsProvider>
    </StatusProvider>
  );
}
