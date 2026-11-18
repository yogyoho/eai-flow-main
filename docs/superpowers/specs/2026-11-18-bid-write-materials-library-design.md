# 素材库独立页 + 废弃 /bid-materials 应用清除 设计(2026-11-18,批卅二)

## 背景与定位(用户裁决)

- bid_write 六类素材实体库(资质/业绩/人员等)的数据面**本来就是 owner 级跨任务**(`/materials` CRUD 只认 owner 不认 task),但界面埋在 ②素材核对页(任务步骤页)底部——定位错位:资产管理被当成了步骤内操作。
- 用户裁决:**B 资产定位**——独立成页;顺带**删除废弃的 `/bid-materials` 应用**(另一套库,已废弃,与写作端实体库互不相通)。
- 导航方案:**A** 挂写作工作环,非步骤资产页;②页留缺口清单+带上下文跳转。

## 架构

### ① 新「素材库」页
- 路由 `/bid-write/materials-library`;新 `LibraryView`(素材核对页底部六类实体库区块整体迁出为独立组件复用):六类过滤 tab、CRUD、指标条。
- 导航:写作环「素材库」入口,无序号(⑥导出后、断言注册表前);角色可见性 taskPage 新键 `materials_library`,先在 `config/permissions.yaml` + `deploy/offline/config/permissions.yaml` 声明。
- 绑定语义不变:页面只管资产 CRUD,「已绑定」仍由断言执行与导出门禁裁决。

### ② 素材核对页瘦身
- 保留:缺口清单(三态)+缺口计数指标+预审查/门禁提示——职责收敛为「动笔前暴露缺件」。
- 缺口行「去素材库补录」跳转带上下文:落地素材库页自动按缺口实体类型过滤定位。
- 页内实体库区块移除;补录动作全导向素材库页。

### ③ 删除废弃 /bid-materials(连根,DB 表不动)
- 前端:`app/bid-materials/` 路由 + `extensions/bid-materials/` 模块(5 文件)。
- 后端:`app/extensions/bid_materials/` 模块(routers/schemas/storage/service/__init__)+ `gateway/app.py` 注册行 + `database.py` 模型引用。
- 权限:两份 permissions.yaml 的 bid_materials 块 + 角色 pages 引用清理。
- 收口:引用 grep 归零(bug-4402 DNR:核对整个模块目录);DB 表与数据**不动**(只摘代码防误删历史数据)。

### ④ 测试
- LibraryView dom 测试:六类过滤/CRUD/带类型跳转落地定位。
- ②页 dom 测试改造:缺口行跳转断言+实体库区块移除断言。
- 删除面:bid-materials 引用归零;e2e 引用清理。
- 全量:bid_write pytest + bid-write rstest + typecheck/eslint。

## 边界诚实
- 不做素材跨任务"引用计数/绑定状态"展示(绑定属断言面,后续批)。
- `/materials` API 本批零改动(前端搬家用而已)。
- bid_materials 旧表数据留存但页面/接口消失——如需历史数据迁移另开批。
