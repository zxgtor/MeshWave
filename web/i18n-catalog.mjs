// Chinese source messages remain stable; only their presentation is localized.
export default `
蓝色 0% 保护 → 金色 100% 完全影响；红色为硬锁定。绘制值决定目标权重，沿用上方半径和强度；权重影响重新几何贴合、手动笔刷、纹理细化和时序平滑。	Blue 0% protection → gold 100% influence; red indicates hard locks. The paint value sets the target weight using the radius and strength above. Weights affect geometry refitting, manual brushes, texture refinement, and temporal smoothing.
模板区行为	Template Region
整体对齐后固定	Keep Aligned
不贴面随动	Follow Neighbors
已切换模板排除区行为，请重新贴合。	Template region behavior changed. Run fitting again.
已撤销模板区域模式切换。	Undid template region mode change.
模板区域模式无效。	Invalid template region mode.
几何软权重必须与模板顶点一一对应，范围为 0–1。	Geometry weights must match template vertices and range from 0 to 1.
不是支持的 Mesh Wave 工程文件（版本 1、2 或 3）。	Unsupported Mesh Wave project (expected version 1, 2, or 3).
Shift + 点击选择区域。模板区行为统一应用于所有模板排除面：红色固定，青色不参与贴面但随周围形变。目标红色区域不参与匹配；对应点及曲线节点所在面不可排除。	Shift-click to select regions. The template mode applies to all excluded template faces: red stays fixed; cyan follows surrounding deformation without fitting. Red target regions are excluded from matching. Faces containing correspondence points or curve controls cannot be excluded.
软权重也参与重新贴合：0% 保持整体对齐位置，1–100% 调节表面吸附；硬对应点优先。先贴合并绘制权重，再重新求解。权重和区域模式随工程及批次保存。	Soft weights also affect refitting: 0% preserves the aligned position; 1–100% controls surface attraction. Hard correspondences take priority. Fit once, paint weights, then solve again. Weights and region mode are saved with projects and batch snapshots.
Mesh Wave · 网格贴合工作台	Mesh Wave · Mesh Fitting Workbench
网格贴合工作台	Mesh Fitting Workbench
界面语言	Interface Language
选点方式	Point Placement
连续表面点	Surface Point
吸附到顶点	Snap to Vertex
面 #	Face #
表面点保存在三角面内部，不吸附顶点；标记随模板形变。求解严格保持重心坐标约束。旧顶点点对仍可编辑。	Surface points are stored inside triangles without vertex snapping; markers follow template deformation. Fitting enforces barycentric equalities. Existing vertex pairs remain editable.
三次表面样条	Cubic Surface Spline
旧版网格折线	Legacy Mesh Polyline
新曲线使用三次插值样条，投射到相连且法线相容的表面，再按弧长生成连续表面点。Shift 点击两侧添加控制点，起点与方向需对应；每侧至少 2 点，3 点以上可产生弯曲。旧工程的网格折线保持原方式。已有结果请先恢复模板。	New curves use interpolating cubic splines projected onto connected, normal-compatible surfaces, then sampled by arc length into continuous surface points. Shift-click both sides to add controls; match starts and direction. Use at least 2 controls per side; 3 or more allow curvature. Legacy project polylines retain their behavior. Restore the template before editing a result.
贴合质量检查	Fit Quality Inspection
计算／刷新误差	Compute / Refresh Errors
显示贴合误差热图	Show Fit Error Heatmap
误差阈值 %	Error Threshold %
标出法线异常（紫色）	Highlight Normal Issues (Purple)
距离单位沿用 OBJ；百分比按目标包围盒对角线计，不假定毫米。统计单向最近三角面距离，不按法线过滤；法线异常单独计数。灰色排除区及未使用顶点不计入统计，对应点保留。	Distances use OBJ units; percentages use the target bounding-box diagonal, not assumed millimeters. Measures one-way nearest-triangle distance without normal filtering; normal issues are counted separately. Gray excluded or unused vertices are omitted; correspondences remain visible.
完成贴合后，计算误差并检查局部区域。	After fitting, compute errors and inspect local regions.
局部检查 · Shift 点击左侧	Local Inspection · Shift-click Left Mesh
局部半径 %	Local Radius %
定位最大误差	Locate Maximum Error
清除局部选择	Clear Local Selection
开启局部检查后，Shift 点击眼周、嘴唇等位置；沿网格边距离选取邻域，邻域外变暗。检查只读，不改点对、模型或撤销历史。几何变化后需重新计算；距离小不代表解剖对应正确，也不检测自相交。	Enable local inspection, then Shift-click an eye, lip, or other region. Neighbors are selected by mesh-edge distance; other vertices are dimmed. Inspection is read-only and preserves pairs, meshes, and undo history. Recompute after geometry edits. Small distances do not prove anatomical correspondence; self-intersections are not detected.
质量检查参数超出范围。	Quality inspection settings are out of range.
几何已变化，请重新计算质量检查。	Geometry changed. Recompute quality inspection.
正在计算完整表面误差…	Computing full surface errors…
检查完成 · 跳过	Inspection complete · Skipped
个模板顶点 · 排除	template vertices · Excluded
个目标面 · 忽略	target faces · Ignored
个退化目标面	degenerate target faces
没有可统计的顶点。	No eligible vertices to summarize.
个顶点 · 超阈值	vertices · Above threshold
平均	Mean
中位数	Median
· P95	· P95
· 最大	· Maximum
法线异常	Normal issues
· 法线未知	· Unknown normals
全局质量	Global Quality
局部质量 · 中心顶点 #	Local Quality · Center Vertex #
表面半径	Surface Radius
表面误差 ·	Surface Error ·
灰色不计入统计 · 紫色法线异常	Gray: omitted · Purple: normal issues
灰色不计入统计 · 红色达到阈值	Gray: omitted · Red: at or above threshold
此处为排除区或未使用顶点，不参与统计。	This vertex is excluded or unused and is omitted from statistics.
未保存	Unsaved
打开工程	Open Project
保存工程	Save Project
载入演示	Load Demo
导入模型	Import Meshes
模板模型	Template Mesh
选择 OBJ 文件	Choose OBJ File
保留此模型的拓扑和 UV	Preserve this mesh's topology and UVs
目标模型	Target Mesh
模板将贴合此模型的表面	Fit the template to this mesh's surface
模板 ≤ 100,000 顶点（高精度需多阶段）	Template ≤ 100,000 vertices (multi-stage for dense meshes)
目标 ≤ 200,000 顶点 · 单文件 ≤ 18 MB	Target ≤ 200,000 vertices · ≤ 18 MB per file
选择对应点	Set Correspondences
0 对	0 pairs
自动识别人脸点	Detect Face Landmarks
先将两侧人脸放大并转到正面。使用灰模渲染检测，无需 UV；先预览建议，再采用或手动修正。已有贴合结果时先恢复原始模板。	Zoom in and face both meshes forward. Detection uses untextured renders; UVs are not required. Review suggestions before accepting or editing. Restore the original template first if a fitted result exists.
尚未自动检测	No detection yet
采用建议 · 替换点对	Accept Suggestions · Replace Pairs
取消建议，保留原点对	Discard Suggestions · Keep Pairs
按住 Shift 点击模板，再点击目标的相同部位。至少 3 对不共线的点。点击列表中的模板点或目标点可重选，点对右侧可删除。	Shift-click the template, then the same location on the target. Use at least 3 non-collinear pairs. Click either side of a listed pair to reselect it, or delete the pair on the right.
撤销一对	Undo Pair
清空	Clear
取消重选	Cancel Reselection
尚未选择对应点	No correspondences selected
曲线对应	Curve Correspondences
新增成对曲线	Add Curve Pair
当前曲线	Current Curve
名称	Name
采样对数	Sample Pairs
闭合曲线（两侧起点需对应）	Closed curve (match starting points)
撤销左节点	Undo Left Point
撤销右节点	Undo Right Point
反转右侧方向	Reverse Right Curve
删除此曲线	Delete Curve
新增后 Shift + 点击两侧模型，依次绘制同一部位；每侧至少 2 个节点。按网格表面折线连接，非平滑样条。节点编号表示方向；过粗网格请减少采样数。已有结果请先恢复原始模板。	Add a curve pair, then Shift-click corresponding features on both meshes. Use at least 2 control points per side. Paths follow mesh edges rather than smooth splines; numbering shows direction. Use fewer samples on coarse meshes. Restore the original template before editing.
生成对应点预览	Preview Correspondences
采用曲线点	Accept Curve Points
取消预览	Cancel Preview
曲线点采用后才参与求解。修改曲线后请重新生成并采用；采用前保留旧点对。	Curve points affect fitting only after acceptance. After editing curves, regenerate and accept the preview. Existing pairs remain until then.
区域排除	Region Exclusions
点击操作	Click Action
对应点	Correspondences
绘制成对曲线	Draw Curve Pairs
排除区域	Exclude Region
恢复区域	Restore Region
选择范围	Selection Area
单个三角面	Single Triangle
周围 1 圈	1 Neighbor Ring
周围 3 圈	3 Neighbor Rings
模板 0 面 · 目标 0 面	Template: 0 faces · Target: 0 faces
撤销区域操作	Undo Region Edit
清空排除	Clear Exclusions
Shift + 点击模型，红色为排除区域。模板区域在整体对齐后固定；目标区域不参与贴合。对应点所在面不可排除。	Shift-click a mesh; excluded faces appear red. Template regions stay fixed after global alignment; target regions are omitted from fitting. Faces containing correspondence points cannot be excluded.
贴合与导出	Fit and Export
求解模式	Solver Mode
多阶段 · 从粗到细	Coarse to Fine
单阶段 · 对照	Single Stage
总迭代预算	Total Iterations
形状保持	Shape Retention
较弱 · 更贴近表面	Low · Closer Fit
标准	Standard
较强 · 更保留形状	High · Preserve Shape
法线夹角	Normal Angle
多阶段先减少形变自由度与匹配采样，最后全顶点精修；保留拓扑和 UV。小模型会跳过不必要的粗层。	Multi-stage solving reduces deformation variables and correspondence samples before refining all vertices. Topology and UVs are preserved. Small meshes skip unnecessary coarse stages.
精确三角面匹配 · 法线过滤 · 防翻面已启用。夹角越小越严格，两侧面朝向需一致。	Exact surface matching, normal filtering, and flip prevention are enabled. Smaller angles are stricter; both meshes need consistent face orientations.
开始非刚性贴合	Start Non-rigid Fitting
导出贴合结果 · OBJ	Export Fitted Mesh · OBJ
恢复原始模板	Restore Original Template
保留顶点顺序、面和 UV。需要配套贴图时，请使用下方“导出纹理模型 · ZIP”。	Preserves vertex order, faces, and UVs. For textures and materials, use Export Textured Mesh · ZIP below.
笔刷修正	Brush Corrections
操作	Tool
浏览模型	Navigate
外推 · 沿法线	Pull · Along Normals
内压 · 反法线	Push · Against Normals
局部平滑	Local Smooth
表面投射	Surface Projection
贴面平滑	Surface Smooth
绘制影响权重	Paint Influence Weights
平滑权重	Smooth Weights
半径 %	Radius %
强度	Strength
绘制值 %	Paint Value %
显示影响权重	Show Influence Weights
蓝色 0% 保护 → 金色 100% 完全影响；红色为硬锁定。绘制值决定目标权重，沿用上方半径和强度；权重影响手动笔刷和纹理细化。	Blue: 0% protected → Gold: 100% influence. Red marks hard constraints. Paint Value sets the desired weight, using the radius and strength above. Weights affect brushes and texture refinement.
全部保护	Protect All
全部可编辑	Enable All
撤销笔刷	Undo Stroke
重做笔刷	Redo Stroke
完成贴合后，选择笔刷并在左侧拖动。	After fitting, choose a brush and drag on the left mesh.
左键拖动修正，Alt + 左键旋转，右键平移，Esc 取消当前笔画。对应点与固定区域锁定；半径按目标尺寸计。投射最远为笔刷半径，沿用贴合法线夹角，跳过目标排除区。修改后需重新烘焙贴图。	Left-drag to edit, Alt + left-drag to rotate, right-drag to pan, Esc to cancel a stroke. Correspondences and fixed template regions are locked. Radius is relative to target size. Projection uses the brush radius and fitting normal angle, skipping excluded target faces. Rebake after geometry edits.
纹理与烘焙	Textures and Baking
模板贴图（预览）	Template Texture (Preview)
选择 PNG / JPEG	Choose PNG / JPEG
目标 / 扫描贴图	Target / Scan Texture
移除模板贴图	Remove Template Texture
移除扫描贴图	Remove Scan Texture
每侧一张贴图，需完整 OBJ UV。输入图 ≤ 8 MB、16 百万像素。先贴合，再烘焙扫描颜色到模板 UV。	One texture per mesh, with complete OBJ UVs. Images: ≤ 8 MB and 16 million pixels. Fit first, then bake scan colors into template UVs.
输出分辨率	Output Resolution
边缘扩展	Edge Padding
投射距离 %	Projection Distance %
距离按目标包围盒对角线计；使用上方的法线夹角。未匹配和排除区保持透明；模板 UV 需不重叠、位于 0–1。	Distance is relative to the target bounding-box diagonal and uses the fitting normal angle. Unmatched and excluded regions stay transparent. Template UVs must be non-overlapping within 0–1.
烘焙扫描纹理到模板 UV	Bake Scan Texture to Template UVs
尚未烘焙	Not baked yet
导出贴图 · PNG	Export Texture · PNG
导出纹理模型 · ZIP	Export Textured Mesh · ZIP
网格诊断与清理	Mesh Diagnostics and Cleanup
模型	Mesh
模板	Template
目标	Target
诊断原始模型	Inspect Original Mesh
检查待修复 OBJ 文件	Inspect an OBJ File
撤销上次修复	Undo Last Repair
检测并高亮非流形边、无效面、孤立点及绕序冲突。普通导入失败的文件也可单独检查。先预览，再选择是否应用修复。	Highlight non-manifold edges, invalid faces, isolated vertices, and winding conflicts. You can inspect files that fail normal import. Preview repairs before applying them.
纹理辅助贴合	Texture-assisted Fitting
先完成几何贴合，左侧调到正面；两侧需完整 UV 和同一人物、相近光照的贴图。模板贴图应来自中性表情，不使用当前目标的烘焙图作匹配。	Fit geometry first and face the left mesh forward. Both meshes need complete UVs and textures of the same person under similar lighting. Use a neutral reference texture for the template, not a texture baked from the current target.
分辨率	Resolution
虚拟视图	Virtual Views
正面及两侧	Front and Sides
仅正面	Front Only
迭代	Iterations
每步位移 %	Step Displacement %
自动生成共用正交视图，沿用对应点、排除区、软权重和防翻面。0% 权重顶点固定；位移按目标尺寸计。	Shared orthographic views are generated automatically. Correspondences, exclusions, soft weights, and flip prevention remain active. Vertices with 0% weight stay fixed; displacement is relative to target size.
计算光流细化预览	Preview Optical Flow Refinement
采用纹理细化	Accept Texture Refinement
未进行纹理细化。预览采用前，原结果与烘焙贴图保留；采用后需重新烘焙。	No texture refinement yet. The original result and baked texture remain until you accept the preview. Rebake after accepting.
批处理与序列	Batches and Sequences
约束模式	Constraint Mode
同拓扑序列 · 复用当前点对	Reuse Current Pairs
不同拓扑扫描 · 独立约束 JSON	Per-scan JSON
选择多个目标 OBJ	Choose Target OBJ Files
选择扫描 / 表情序列	Choose Scans / Expression Sequence
尚未选择扫描。	No scans selected.
将当前贴合结果作为本批模板	Use Current Result as Batch Template
同拓扑模式核对顶点数量及面索引顺序；顶点编号仍须对应相同部位。不同拓扑扫描需先各自建立点对，再导出并加载约束 JSON。	Same-topology mode checks vertex counts and face index order; vertex IDs must still represent corresponding locations. For different topologies, set pairs for each scan, then export and load its constraints JSON.
导出当前扫描约束 JSON	Export Scan Constraints JSON
加载一个或多个约束 JSON	Load Constraints JSON Files
选择独立扫描约束	Choose Per-scan Constraints
约束按扫描文件名匹配，并核对模板拓扑。	Constraints are matched by scan filename and checked against template topology.
跨帧时序平滑 · 减少局部形变抖动	Temporal Smoothing · Reduce Jitter
时序模式	Temporal Mode
单向 · 参考上一帧	Forward · Previous Frame
双向 · 结合前后帧	Bidirectional · Neighboring Frames
平滑强度 %	Smoothing Strength %
最大修正 %	Max Correction %
自适应强度 · 快速表情减少平滑	Adaptive Strength · Preserve Fast Motion
速度阈值 % / 帧	Speed Threshold % / Frame
检测异常帧 · 隔离噪声和贴合跳变	Detect Anomalies · Isolate Noise and Jumps
异常偏差阈值 %	Anomaly Threshold %
修复异常帧并重新烘焙	Repair Anomalies and Rebake
连续修复上限	Max Consecutive Repairs
修复会自动开启检测和烘焙。使用前后原本正常的帧插值，再按本帧点对、固定区和软权重重新贴合；修复后重新检查，合格才烘焙。缺少前后参考、异常段过长或检查失败时继续隔离。原扫描及原异常缓存保留，修复不消除扫描本身的噪声或恢复缺失纹理。	Repair enables detection and baking. Interpolate between original normal neighbors, then refit with this frame's pairs, fixed regions, and soft weights. Only validated repairs are baked. Missing neighbors, long anomaly runs, or failed checks remain isolated. Original scans and anomaly caches are retained; repair does not remove scan noise or recover missing textures.
启用后先收集序列，再比较扫描粗糙度、离面误差和局部不连贯跳变。未修复的可疑帧保留已有几何和约束，跳过平滑/烘焙并切断历史；报告列出原因。边界、短片段或不同扫描拓扑可能上下文不足；检测不能可靠区分所有大幅噪声与真实运动，需复查。	Collect the sequence before comparing scan roughness, surface error, and incoherent local jumps. Unrepaired suspect frames keep their geometry and constraints but skip smoothing/baking and break history. Reports list reasons. Boundaries, short clips, or topology changes may lack context. Review results: detection cannot always distinguish large noise from real motion.
自适应时，上方强度作为上限。先补偿姿态，再按局部表情速度降低强度；达到阈值的区域停止平滑，保留快速峰值。阈值以目标尺寸百分比/相邻帧计，越低越早保护运动。大幅扫描噪声也可能被当作运动，仍需检查结果。	Adaptive mode treats the strength above as a maximum. After pose compensation, faster local motion gets less smoothing; regions at the threshold remain unsmoothed. Speed is a percentage of target size per neighboring frame. Lower thresholds protect motion sooner. Large scan noise can resemble motion, so inspect the results.
用于连续、等间隔的同一人物序列，按文件名数字顺序处理。双向先收集贴合/光流结果，再结合相邻前后帧；片段首尾保留原几何，至少 3 帧才有可平滑的中间帧。先补偿姿态与尺度，保留本帧硬点、排除区、软权重和防翻面约束，最后烘焙。失败切断片段；强平滑可能削弱快速表情峰值，请为片段切换另建批次。	Use continuous, equally spaced frames of one person, processed in numeric filename order. Bidirectional mode collects fits/flow results, then combines neighbors. Segment endpoints stay unchanged; at least 3 frames are needed. Pose and scale are compensated while preserving this frame's hard points, exclusions, weights, and flip prevention. Baking follows smoothing. Failures split segments; strong smoothing can reduce expression peaks. Use separate batches for cuts.
双向收集阶段取消：完成已收集前缀的平滑/烘焙。平滑阶段取消：完成当前帧，剩余帧保留未平滑几何并跳过烘焙。	Cancel during bidirectional collection: finish smoothing/baking the collected prefix. Cancel during smoothing: finish the current frame; remaining frames keep unsmoothed geometry and skip baking.
同一人物表情序列 · 逐帧光流细化并自动烘焙	Same-person Expressions · Optical Flow and Baking
使用第 06 节加载的模板参考贴图；请先将左侧模型转到正面。共用第 08 节光流参数、当前左侧相机朝向和软权重；几何与光流独立求解，启用时序后再跨帧平滑。	Uses the template reference texture from section 06. Face the left mesh forward. Reuses optical flow settings from section 08, the left camera direction, and soft weights. Geometry and flow are solved independently per frame; temporal smoothing follows if enabled.
启用光流后自动开启烘焙。无法验证纹理改善的帧记为失败，保留几何并跳过烘焙，继续下一帧。遮挡、嘴内或光照差异仍需人工检查。	Optical flow enables baking. Frames without a verified texture improvement are marked failed; geometry is retained and baking skipped before continuing. Inspect occlusions, mouth interiors, and lighting differences manually.
每项贴合后烘焙扫描纹理到模板 UV	Bake Each Scan to Template UVs
选择扫描贴图 PNG / JPEG	Choose Scan Textures · PNG / JPEG
选择多张扫描贴图	Choose Multiple Scan Textures
未选择贴图。	No textures selected.
按主名匹配（scan01.obj → scan01.png），每个扫描一张贴图；同名多图视为歧义。共用第 06 节的分辨率、边缘扩展、投射距离及当前法线夹角。模板和扫描均需有效 UV；烘焙失败保留几何并继续。	Match by basename (scan01.obj → scan01.png), one texture per scan. Multiple matching images are ambiguous. Reuses section 06 resolution, padding, projection distance, and the current normal angle. Both meshes need valid UVs. Baking failures retain geometry and processing continues.
完成后自动下载 ZIP（含部分成功结果）	Download ZIP Automatically (Including Partial Results)
开始批处理	Start Batch
完成当前项后取消	Cancel After Current Item
下载结果 ZIP	Download Results ZIP
重新查询任务	Refresh Job
清空所选队列	Clear Selection
尚未启动批处理。	No batch started.
每批最多 50 项，单 OBJ ≤ 18 MB，单贴图 ≤ 8 MB / 16 百万像素，上传及未压缩输出各 ≤ 256 MB。按文件名数字顺序求解；勾选烘焙后导出各项 OBJ、MTL、PNG 和报告。建议启动前保存工程；关闭页面后后台继续，本地服务停止则中断。	Up to 50 items per batch, ≤ 18 MB per OBJ, ≤ 8 MB / 16 million pixels per texture, and ≤ 256 MB each for uploads and uncompressed outputs. Solved in numeric filename order. Baking exports OBJ, MTL, PNGs, and reports. Save your project first. Closing the page leaves jobs running; stopping the local service interrupts them.
准备模型	Prepare Meshes
导入两个模型，或载入演示体验完整流程	Import two meshes, or load the demo to try the workflow
纹理	Textures
原色	Unlit
线框	Wireframe
叠加目标	Overlay Target
视图复位	Reset View
贴合结果	Fitted Result
导入模板模型	Import Template Mesh
顶点与拓扑将保留	Vertex order and topology are preserved
导入目标模型	Import Target Mesh
选择与模板相同的部位	Choose the same region as the template
就绪	Ready
拖动旋转 · 滚轮缩放 · 右键平移 · Shift + 点击执行所选操作	Drag to rotate · Scroll to zoom · Right-drag to pan · Shift-click for selected action
网格诊断	Mesh Diagnostics
关闭	Close
非流形边/点	Non-manifold Edges / Vertices
无效面	Invalid Faces
孤立点	Isolated Vertices
绕序冲突	Winding Conflicts
拖动旋转 · 滚轮缩放 · 右键平移。无有效坐标或索引的面无法定位，请看下方原文件行号。	Drag to rotate, scroll to zoom, right-drag to pan. Faces without valid coordinates or indices cannot be located; see original file line numbers below.
修复策略：删除无效/重复面及孤立点，分离非流形连接，统一局部绕序。输出会三角化，分离处可能形成开放边界。	Repair removes invalid/duplicate faces and isolated vertices, splits non-manifold connections, and aligns local winding. Output is triangulated; splits can create open boundaries.
生成修复预览	Preview Repair
查看原始	View Original
下载修复 OBJ	Download Repaired OBJ
应用修复并清空约束	Apply Repair and Clear Constraints
烘焙贴图预览	Baked texture preview
`.trim().split('\n').map(line=>line.split('\t'));
