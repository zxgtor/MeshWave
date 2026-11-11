# REA 调查与实现边界

## 已观察的本机证据

- 安装项：Faceform Wrap 2025.11.14，路径 `C:\Program Files\Faceform\Wrap 2025.11.14`。
- REA `inspect_desktop_application` 保留证据 `ev_eac667174f9ebffcd1103f5b9c9690d7406ac92eee33d7514537721b6a8928a0`；摘要证据 `ev_764f57aae7d961e0b2269db8fdd7b59e043148812bb87c4c3d28e0e2a90e7f1a`。扫描 6,536 项，探测 220 个文件、读取 73,112 字节；没有确立运行行为。目录摘要只覆盖元数据与读取范围，不是全部文件内容的哈希。
- REA `inspect_pe_imports` 证据 `ev_2a2f72aee720da8e0334b4e4859a9d7eb23c0ce43b5d909cca090b9fe15b16af`。`Wrap.exe` 为 AMD64 PE32+，35,265,144 字节，SHA-256 `a7a079eac386c892b37981f833538830346de8e01703bc50456597f24bec76a9`；导入表包含 42 个 DLL、3,551 个函数。
- 导入依赖包括 Qt5、OpenGL、Embree、MKL、OpenBLAS、OpenCV、ONNX Runtime、Python 3.9、FBX 和 Alembic。导入表仅证明静态依赖声明，不证明对应功能运行时可达。
- 本地 JSON 示例 `Gallery\Projects\Wrapping.wrap` 包含 `LoadGeom`、`SelectPointPairs`、`SelectPolygons`、`FastWrapping`。FastWrapping 参数包括浮动/固定几何、对应点、平滑与拟合权重、ICP 与优化迭代次数。这是文件中观察到的配置，不是算法源码。

## 首版的自主设计选择

- 用本地 Python 数值后端和 Three.js 双视图实现用户选定的四步流程。
- 模板/目标 OBJ、顶点对应点、相似变换、目标表面采样、硬点约束与拉普拉斯位移平滑。
- 采用 SciPy 稀疏直接求解器，不声称等同于原版 FastWrapping。
- 演示几何由本项目独立生成。未复制原版界面资源、模型、库或专有实现。

## 尚未验证

原版核心算法、实际运行时交互、原版质量与性能、原生工程格式兼容性。没有进行原版二进制反编译或逐行为对照；本次 REA 调查是结构与文件配置调查。

## 设计约束

工作台面向三维模型操作，深色低干扰界面；差异度 3/10、动效 1/10、密度 7/10。主视觉是双三维视图；左栏按导入、对应点、贴合导出排列。始终保证两侧角色清楚、点对编号一致、计算中防止修改输入。小屏上下排列视图。避免营销区域和无关节点功能。
