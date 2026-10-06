import { defineConfig } from "vitepress";

// 部署于 nginx /ontostudio/docs/ 子路径（独立静态容器 ontostudio-docs:3011）
export default defineConfig({
  lang: "zh-CN",
  title: "OntoStudio 文档中心",
  description: "本体系统操作指南 · 概念详解 · MCP/国标参考 · 业务本体设计",
  base: "/ontostudio/docs/",
  ignoreDeadLinks: true, // 期3 内容齐后改 false（docs 升级 spec §7）
  themeConfig: {
    siteTitle: "OntoStudio 文档中心",
    nav: [
      { text: "首页", link: "/" },
      { text: "功能操作", link: "/guide/" },
      { text: "术语解释", link: "/glossary/" },
      { text: "概念详解", link: "/concepts/" },
      { text: "参考", link: "/reference/mcp-tools" },
      { text: "业务本体设计", link: "/design/eia-model" },
      { text: "更新记录", link: "/changelog" },
    ],
    sidebar: {
      "/guide/": [
        {
          text: "功能操作",
          items: [
            { text: "模块地图", link: "/guide/" },
            { text: "端到端数据流", link: "/guide/data-flow" },
            { text: "审阅闭环", link: "/guide/review-loop" },
            { text: "01 工作台总览", link: "/guide/01-dashboard" },
            { text: "02 图谱浏览", link: "/guide/02-graph" },
            { text: "03 实体库", link: "/guide/03-entities" },
            { text: "04 消解审核", link: "/guide/04-resolve" },
            { text: "05 本体建模器", link: "/guide/05-modeler" },
            { text: "06 推理工作台", link: "/guide/06-reasoning" },
            { text: "07 校验中心", link: "/guide/07-validation" },
            { text: "08 抽取导入", link: "/guide/08-ingest" },
            { text: "09 导出互操作", link: "/guide/09-export" },
          ],
        },
      ],
      "/concepts/": [
        {
          text: "概念详解",
          items: [
            { text: "阅读顺序", link: "/concepts/" },
            { text: "本体地基：三元组与 RDFS/OWL", link: "/concepts/foundations" },
            { text: "Turtle 与 JSON-LD 1.1", link: "/concepts/turtle-jsonld" },
            { text: "SHACL", link: "/concepts/shacl" },
            { text: "owlrl 闭包", link: "/concepts/owlrl" },
            { text: "SPARQL 与 CONSTRUCT 派生", link: "/concepts/sparql-construct" },
            { text: "TriG 快照", link: "/concepts/trig-snapshots" },
          ],
        },
      ],
      "/reference/": [
        {
          text: "参考",
          items: [
            { text: "MCP 工具总表", link: "/reference/mcp-tools" },
            { text: "GB/T 48000.3—2026 符合性", link: "/reference/gbt-48000" },
            { text: "Agent 集成指南", link: "/reference/agent-integration" },
          ],
        },
      ],
      "/glossary/": [
        {
          text: "术语解释",
          items: [
            { text: "术语总览", link: "/glossary/" },
            { text: "eia 域（环评）", link: "/glossary/eia" },
            { text: "doc_graph 域（文档图谱）", link: "/glossary/doc-graph" },
          ],
        },
      ],
      "/design/": [
        {
          text: "业务本体设计",
          items: [
            { text: "eia 域模型", link: "/design/eia-model" },
            { text: "doc_graph 骨架", link: "/design/doc-graph" },
          ],
        },
      ],
      "/guide/": [
        {
          text: "功能操作",
          items: [{ text: "九大模块操作指南", link: "/guide/" }],
        },
      ],
      "/": [
        {
          text: "总览",
          items: [
            { text: "首页", link: "/" },
            { text: "更新记录", link: "/changelog" },
          ],
        },
      ],
    },
    search: {
      // 本地全文搜索——内网/离线环境可用，无外部服务依赖
      provider: "local",
      options: {
        translations: {
          button: { buttonText: "搜索文档", buttonAriaLabel: "搜索文档" },
          modal: {
            noResultsText: "未找到结果",
            resetButtonTitle: "清除查询",
            footer: { selectText: "选择", navigateText: "切换", closeText: "关闭" },
          },
        },
      },
    },
    outline: [2, 3],
  },
});
