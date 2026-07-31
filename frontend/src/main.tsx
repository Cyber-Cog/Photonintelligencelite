import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { AuthProvider } from "@/context/AuthContext";
import { DemoTourProvider } from "@/context/DemoTourContext";
import { JobProvider } from "@/context/JobContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { WorkflowTransitionProvider } from "@/context/WorkflowTransitionContext";
import "@/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <JobProvider>
            <WorkflowTransitionProvider>
              <DemoTourProvider>
                <App />
              </DemoTourProvider>
            </WorkflowTransitionProvider>
          </JobProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
