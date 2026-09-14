import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { TabBar } from "./components/TabBar";
import { StatusProvider } from "./StatusContext";
import { SettingsProvider } from "./SettingsContext";
import Learn from "./pages/Learn";
import LessonPlayer from "./pages/learn/LessonPlayer";
import ZhuyinCourse from "./pages/learn/ZhuyinCourse";
import ZhuyinLesson from "./pages/learn/ZhuyinLesson";
import Read from "./pages/Read";
import Review from "./pages/Review";
import Listen from "./pages/Listen";
import Speak from "./pages/Speak";
import Talk from "./pages/Talk";
import Me from "./pages/Me";

export default function App() {
  // Hide the tab bar during a lesson so the exercise gets the full screen.
  //
  // Matched narrowly on purpose: /learn/zhuyin is a course *index*, not a
  // lesson, and a bare /^\/learn\/.+/ would strand it with no navigation.
  const location = useLocation();
  const inLesson =
    /^\/learn\/zhuyin\/.+/.test(location.pathname) ||
    (/^\/learn\/.+/.test(location.pathname) && location.pathname !== "/learn/zhuyin");

  return (
    <StatusProvider>
      <SettingsProvider>
        <div className="mx-auto flex min-h-screen max-w-xl flex-col">
          <main className="flex-1 pb-2">
            <Routes>
              <Route path="/" element={<Navigate to="/learn" replace />} />
              <Route path="/learn" element={<Learn />} />
              {/* Before the :lessonId route so the literal segment wins. */}
              <Route path="/learn/zhuyin" element={<ZhuyinCourse />} />
              <Route path="/learn/zhuyin/:lessonId" element={<ZhuyinLesson />} />
              <Route path="/learn/:lessonId" element={<LessonPlayer />} />
              <Route path="/read" element={<Read />} />
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
