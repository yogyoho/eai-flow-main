/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import express from "express";
import path from "path";
import { fileURLToPath } from "url";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";
import { Task, Project, NotificationLog, CalendarEvent } from "./src/types.js";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Initialize Gemini SDK with telemetry header
const apiKey = process.env.GEMINI_API_KEY;
let ai: GoogleGenAI | null = null;
if (apiKey) {
  ai = new GoogleGenAI({
    apiKey: apiKey,
    httpOptions: {
      headers: {
        'User-Agent': 'aistudio-build',
      },
    },
  });
}

// In-memory Database to persist session alterations
let tasks: Task[] = [
  {
    id: "task-1",
    title: "神经网络主核超参数微调 (Hyperparameter Tuning for Neural Grid)",
    description: "Align core node constraints and weight arrays with simulated sandbox telemetry.",
    category: "Compute",
    status: "completed",
    priority: "high",
    updatedAt: "2026-06-20",
  },
  {
    id: "task-2",
    title: "安全沙箱漏洞防御机制审计 (Security Sandbox Vulnerability Audit)",
    description: "Audit incoming protocols for deep-packet anomalies in node structures.",
    category: "Security",
    status: "completed",
    priority: "critical",
    updatedAt: "2026-06-20",
  },
];

let projects: Project[] = [
  {
    id: "proj-liaoyang",
    name: "辽阳石化-E2E最终",
    description: "高危化加工工艺单元，消防与防灾大纲2.0编制项目，当前进入人工核验确认环节。",
    progress: 100,
    status: "completed",
    systemLoad: 12,
    coreNodes: 34,
  },
  {
    id: "proj-1",
    name: "量子共振矩阵 (Project Resonance Matrix)",
    description: "Multi-dimensional grid alignment for real-time secure communication threads.",
    progress: 74,
    status: "active",
    systemLoad: 42,
    coreNodes: 8,
  },
  {
    id: "proj-2",
    name: "生物形态特征分类器 (Biomorphic Feature Classifier)",
    description: "Deep learning models classifying non-standard biological patterns with low latency.",
    progress: 35,
    status: "review",
    systemLoad: 68,
    coreNodes: 12,
  },
  {
    id: "proj-3",
    name: "星环轨道遥感解译器 (Aegis Orbital Interpreter)",
    description: "Decoupling dense radar telemetry payloads for geo-spatial spatial rendering.",
    progress: 92,
    status: "completed",
    systemLoad: 12,
    coreNodes: 4,
  }
];

let notifications: NotificationLog[] = [
  {
    id: "notif-1",
    title: "Phase task-178075108605 Ingress Completed",
    description: "Workflow phase task-178075108605 validated across 4 cluster regions.",
    timestamp: "2026/06/20 14:15",
    category: "workflow",
    unread: true,
    actionUrl: "#",
  },
  {
    id: "notif-2",
    title: "System Telemetry: Quantum Calibration Successful",
    description: "Harmonic frequencies locked. Stability calculated at 99.987%.",
    timestamp: "2026/06/20 12:04",
    category: "system",
    unread: true,
    actionUrl: "#",
  },
  {
    id: "notif-3",
    title: "Workflow completed: Neural Net Pre-train Route 9A",
    description: "The pre-training workflow for the feature recognition sub-module finalized.",
    timestamp: "2026/06/19 18:32",
    category: "workflow",
    unread: true,
    actionUrl: "#",
  },
  {
    id: "notif-4",
    title: "Security sandbox shield updated to Rev. 4.09",
    description: "Threat filters deployed and linked to hot-route API ports.",
    timestamp: "2026/06/19 09:12",
    category: "security",
    unread: false,
    actionUrl: "#",
  }
];

let calendarEvents: CalendarEvent[] = [
  {
    id: "cal-1",
    title: "集群抗压峰值审计 (Cluster Load Balancing Review)",
    date: "2026-06-20",
    time: "15:00",
    type: "review",
    loadFactor: 0.85,
  },
  {
    id: "cal-2",
    title: "次代多模态星图节点部署 (Next-Gen Star-Map Node Deployment)",
    date: "2026-06-24",
    time: "02:30",
    type: "deployment",
    loadFactor: 0.92,
  },
  {
    id: "cal-3",
    title: "全区漏洞黑盒扫描 (Inter-subsystem Pen-scan)",
    date: "2026-06-28",
    time: "09:00",
    type: "security",
    loadFactor: 0.45,
  }
];

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // 1. Static API endpoints
  app.get("/api/dashboard", (req, res) => {
    // Dynamically calculate metrics
    const activeProjects = projects.filter(p => p.status === "active" || p.status === "review").length;
    const pendingReviews = projects.filter(p => p.status === "review").length;
    const draftsInProgress = tasks.filter(t => t.status === "pending").length;
    const overdueTasks = tasks.filter(t => t.status === "pending" && t.priority === "critical").length;

    // Emulate organic fluctuating telemetry
    const cpuUsage = Math.floor(45 + Math.random() * 15);
    const memoryUsage = Math.floor(62 + Math.random() * 8);
    const networkTraffic = Math.floor(250 + Math.random() * 80);

    res.json({
      tasks,
      projects,
      notifications,
      calendarEvents,
      metrics: {
        activeProjects,
        pendingReviews,
        draftsInProgress,
        overdueTasks
      },
      telemetry: {
        cpuUsage,
        memoryUsage,
        networkTraffic,
        sandBoxSecurityStatus: "optimal"
      }
    });
  });

  // Toggle tasks status
  app.put("/api/tasks/:id/toggle", (req, res) => {
    const { id } = req.params;
    const task = tasks.find(t => t.id === id);
    if (task) {
      task.status = task.status === "completed" ? "pending" : "completed";
      task.updatedAt = new Date().toISOString().split("T")[0];
      return res.json({ success: true, task });
    }
    return res.status(404).json({ error: "Task not found" });
  });

  // Add new task
  app.post("/api/tasks", (req, res) => {
    const { title, description, category, priority } = req.body;
    if (!title) {
      return res.status(400).json({ error: "Title is required" });
    }
    const newTask: Task = {
      id: `task-${Date.now()}`,
      title,
      description: description || "Auto-initiated protocol sequence.",
      category: category || "Compute",
      status: "pending",
      priority: priority || "medium",
      updatedAt: new Date().toISOString().split("T")[0]
    };
    tasks.unshift(newTask);

    // Also trigger an automatic short notification log
    notifications.unshift({
      id: `notif-${Date.now()}`,
      title: `Task initiated: ${title.substring(0, 30)}...`,
      description: `Task created and allocated on scheduling nodes. Category: ${category}.`,
      timestamp: new Date().toISOString().replace("T", " ").substring(0, 16),
      category: "workflow",
      unread: true
    });

    return res.json({ success: true, task: newTask });
  });

  // Delete task
  app.delete("/api/tasks/:id", (req, res) => {
    const { id } = req.params;
    const lenBefore = tasks.length;
    tasks = tasks.filter(t => t.id !== id);
    if (tasks.length < lenBefore) {
      return res.json({ success: true });
    }
    return res.status(404).json({ error: "Task not found" });
  });

  // Create new project
  app.post("/api/projects", (req, res) => {
    const { name, description, status, systemLoad, coreNodes } = req.body;
    if (!name) {
      return res.status(400).json({ error: "Project name is required" });
    }
    const newProject: Project = {
      id: `proj-${Date.now()}`,
      name,
      description: description || "No deep operational metadata provided.",
      progress: Math.floor(Math.random() * 15), // starts small, 0-15%
      status: status || "active",
      systemLoad: systemLoad ? parseInt(systemLoad) : 30,
      coreNodes: coreNodes ? parseInt(coreNodes) : 2
    };
    projects.unshift(newProject);

    // Trigger notification
    notifications.unshift({
      id: `notif-${Date.now()}`,
      title: `Project matrix initialized: ${name}`,
      description: `Dynamic sub-clusters established with ${coreNodes || 2} nodes. Allocation load: ${systemLoad || 30}%.`,
      timestamp: new Date().toISOString().replace("T", " ").substring(0, 16),
      category: "system",
      unread: true
    });

    return res.json({ success: true, project: newProject });
  });

  // Mark all notifications read
  app.post("/api/notifications/clear-all", (req, res) => {
    notifications.forEach(n => n.unread = false);
    return res.json({ success: true, message: "All notifications declared read." });
  });

  // Set single notification read
  app.post("/api/notifications/:id/read", (req, res) => {
    const { id } = req.params;
    const notif = notifications.find(n => n.id === id);
    if (notif) {
      notif.unread = false;
      return res.json({ success: true });
    }
    return res.status(404).json({ error: "Notification not found" });
  });

  // Schedule new calendar event
  app.post("/api/calendar/events", (req, res) => {
    const { title, date, time, type, loadFactor } = req.body;
    if (!title || !date) {
      return res.status(400).json({ error: "Title and Date are required." });
    }
    const newEvent: CalendarEvent = {
      id: `cal-${Date.now()}`,
      title,
      date,
      time: time || "12:00",
      type: type || "meeting",
      loadFactor: loadFactor ? parseFloat(loadFactor) : 0.5
    };
    calendarEvents.push(newEvent);

    notifications.unshift({
      id: `notif-${Date.now()}`,
      title: `Event scheduled: ${title}`,
      description: `Tactical event slotted for timestamp: ${date} ${time || ""}.`,
      timestamp: new Date().toISOString().replace("T", " ").substring(0, 16),
      category: "workflow",
      unread: true
    });

    return res.json({ success: true, event: newEvent });
  });

  // AI Diagnostic Core utilizing server-side standard model: gemini-3.5-flash
  app.post("/api/gemini/analyze", async (req, res) => {
    if (!ai) {
      return res.status(503).json({
        error: "AI_OFFLINE",
        message: "Gemini API operations offline. Configure your GEMINI_API_KEY inside Settings > Secrets."
      });
    }

    const { customQuery } = req.body;

    // Build the system diagnostic context
    const statsContext = {
      totalTasks: tasks.length,
      pendingTasks: tasks.filter(t => t.status === "pending").length,
      activeProjectsCount: projects.length,
      allProjects: projects.map(p => ({ name: p.name, progress: `${p.progress}%`, status: p.status, load: `${p.systemLoad}%` })),
      serverTime: new Date().toISOString(),
      userQuery: customQuery || "Perform general structural health diagnostic"
    };

    const promptText = `
      You are the Prometheus Stardeck AI Core, the primary tactical neural companion of this highly sophisticated cyber control center.
      The operator is asking: "${statsContext.userQuery}".

      Here is our active system registry:
      - Active projects: ${JSON.stringify(statsContext.allProjects)}
      - Incomplete queue actions: ${statsContext.pendingTasks} out of ${statsContext.totalTasks} total logged procedures.
      - Temporal synchronicity coordinates: ${statsContext.serverTime}

      Respond strictly in a highly futuristic, computer-system stylized narrative (a crisp sci-fi advisor, mixed with professional technical precision, in Chinese language predominantly with occasional scientific/technical English terms).
      Provide:
      1. A custom system diagnostic report header (e.g. AI CORE ANALYZER // STATUS: CHRONOS-7).
      2. Direct sci-fi tactical assessment of what the statistics tell us about current projects and tasks. Mention specific project names that are in-flight!
      3. Precise recommendations (e.g., node reallocation, protocol upgrades, task completions) styled structurally with monospaced accents.
      4. Avoid marketing text, fluff, or generic greetings. Be direct, sleek, cybernetic, and highly authoritative. Keep it extremely cool and concise.
    `;

    try {
      const response = await ai.models.generateContent({
        model: "gemini-3.5-flash",
        contents: promptText,
        config: {
          temperature: 0.82,
        }
      });

      const adviceText = response.text || "Diagnostic compilation failed due to cosmic trace noise (empty response).";
      return res.json({ success: true, response: adviceText });
    } catch (err: any) {
      console.error("Gemini API call failed:", err);
      return res.status(500).json({
        error: "COMPILATION_ERROR",
        message: err.message || "Deep neural net handshake failed. Check your cloud run egress configuration."
      });
    }
  });


  // 2. Vite and Static Handlers
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[SYS_COM] High-grade server active at URL: http://localhost:${PORT}`);
  });
}

startServer();
