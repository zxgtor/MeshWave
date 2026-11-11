export default `
扫描尺寸无效，无法检测异常。	Invalid scan dimensions for anomaly detection.
待检测的贴合顶点无效。	Invalid fitted vertices for detection.
扫描尺寸无效，无法检测贴合质量。	Invalid scan dimensions for fit quality checks.
异常检测邻帧顶点无效。	Invalid neighboring frame vertices for anomaly detection.
扫描名称必须是不含路径的 OBJ 文件名。	Scan name must be an OBJ filename without a path.
批处理参数无效。	Invalid batch settings.
批处理迭代为 5–50 次。	Batch iterations must be 5–50.
批处理求解模式无效。	Invalid batch solver mode.
每项需要 3–100 对对应点。	Each item needs 3–100 correspondence pairs.
批处理对应点	Batch correspondences
扫描表面噪声突增	Sudden increase in scan surface noise
贴合偏离目标表面	Fit deviates from target surface
不连贯的局部贴合跳变	Incoherent local fitting jump
批处理平滑强度或法线夹角无效。	Invalid batch smoothing strength or normal angle.
批处理对应点存在重复索引。	Batch correspondences contain duplicate indices.
批处理任务编号无效。	Invalid batch job ID.
每批最多 50 个扫描。	Up to 50 scans per batch.
队列文件名重复。	Duplicate filenames in the queue.
缺少批处理模板。	Missing batch template.
模板上限为 18 MB。	Template size limit is 18 MB.
模板超过 100,000 顶点。	Template exceeds 100,000 vertices.
超过 25,000 顶点请使用多阶段模式。	Use multi-stage mode above 25,000 vertices.
带贴图输出超过 256 MB 上限，请拆分批次。	Textured output exceeds 256 MB. Split the batch.
任务不存在；请检查本地服务或重新开始。	Job not found. Check the local service or start again.
批量烘焙参数无效。	Invalid batch baking settings.
批量烘焙参数超出范围。	Batch baking settings are out of range.
模板排除面	Template excluded faces
时序平滑软权重无效。	Invalid temporal smoothing soft weights.
批量光流细化需要开启烘焙，并提供参考贴图及光流参数。	Batch optical flow requires baking, a reference texture, and flow settings.
批量光流软权重无效。	Invalid batch optical flow soft weights.
批处理模式无效。	Invalid batch mode.
尚有多个未结束批次，请先取消或完成已有任务。	Multiple unfinished batches exist. Cancel or finish them first.
该任务已不能添加扫描。	Scans can no longer be added to this job.
队列有重复文件名，请重命名后重新加入。	Duplicate queue filenames. Rename the files and add them again.
该扫描不在创建时的队列内。	This scan is not in the original queue.
任务没有可启动的扫描队列。	No scan queue available to start.
尚有扫描未上传，不能启动。	Upload all scans before starting.
已有计算正在进行，请稍后再启动批处理。	A computation is already running. Start the batch later.
批处理尚未完成打包。	Batch packaging is not complete.
目标排除面	Target excluded faces
扫描约束 JSON 与当前模板拓扑不匹配。	Scan constraints JSON does not match the current template topology.
扫描约束 JSON 需要 1–50 项。	Scan constraints JSON must contain 1–50 items.
上传错误信息无效。	Invalid upload error information.
扫描文件内容无效。	Invalid scan file content.
单扫描上限 18 MB，每批上传总量上限 256 MB。	Scans are limited to 18 MB each and batch uploads to 256 MB total.
双向平滑输出超过 256 MB 上限。	Bidirectional smoothing output exceeds 256 MB.
修复输出超过 256 MB 上限。	Repair output exceeds 256 MB.
扫描约束项格式无效。	Invalid scan constraint item format.
扫描约束 JSON 存在重复文件名。	Duplicate filenames in scan constraints JSON.
模型与贴图上传总量超过 256 MB，请拆分批次。	Total mesh and texture uploads exceed 256 MB. Split the batch.
已停止；保留未平滑、未烘焙的几何。	Stopped; unsmoothed, unbaked geometry retained.
已取消修复。	Repair cancelled.
缺少前后可用正常帧，或连续异常超过修复上限。	Missing usable normal neighbors, or anomaly run exceeds the repair limit.
重新贴合后仍有几何异常，未采用修复：	Geometry remains anomalous after refitting; repair rejected:
批量输出超过 256 MB 上限，请拆分批次。	Batch output exceeds 256 MB. Split the batch.
已取消。	Cancelled.
目标拓扑或顶点数量与参考目标不一致，不能复用旧目标索引。	Target topology or vertex count differs from the reference. Target indices cannot be reused.
没有该扫描的独立对应点 JSON。	No per-scan correspondence JSON for this scan.
本地服务停止，未完成；请另建批次重试。	Local service stopped before completion. Retry in a new batch.
异常检测失败（几何已保留）：	Anomaly detection failed (geometry retained):
输出达到 256 MB 上限，请拆分批次。	Output reached 256 MB. Split the batch.
光流细化输出超过 256 MB 上限，请拆分批次。	Optical flow output exceeds 256 MB. Split the batch.
时序平滑输出超过 256 MB 上限，请拆分批次。	Temporal smoothing output exceeds 256 MB. Split the batch.
任务异常停止。	Job stopped unexpectedly.
（几何已保留）：	(geometry retained):
离面误差超过阈值	Surface error exceeds threshold
几何已修复，重新烘焙失败：	Geometry repaired, but rebaking failed:
可疑异常帧，已隔离（保留已有几何和约束，未平滑/烘焙）：	Suspected anomaly isolated (geometry and constraints retained; no smoothing/baking):
烘焙失败	Baking failed
双向平滑失败	Bidirectional smoothing failed
。原错误：	. Original error:
烘焙输入无效（几何已保留）：	Invalid baking input (geometry retained):
光流细化失败（几何已保留，未烘焙）：	Optical flow failed (geometry retained; not baked):
时序平滑失败（几何已保留）：	Temporal smoothing failed (geometry retained):
烘焙失败（几何已保留）：	Baking failed (geometry retained):
笔刷参数格式无效。	Invalid brush settings format.
笔刷需要有效的对应点。	Brushes require valid correspondences.
对应点索引无效或重复。	Invalid or duplicate correspondence indices.
贴合结果顶点无效。	Invalid fitted vertices.
模型尺寸无效。	Invalid mesh dimensions.
当前结果未通过防翻面检查，请重新贴合后再使用笔刷。	Current result failed flip-prevention checks. Refit before using brushes.
当前结果的对应点或固定区已偏离约束，请重新贴合。	Current correspondences or fixed regions violate constraints. Refit the mesh.
最多支持 12 对曲线。	Up to 12 curve pairs are supported.
曲线路径回折或重复经过顶点，请调整控制节点顺序。	Curve path doubles back or repeats vertices. Reorder its control points.
开放曲线每侧至少 2 个节点，闭合曲线每侧至少 3 个节点。	Open curves need at least 2 control points per side; closed curves need at least 3.
曲线长度为零。	Curve length is zero.
采样后顶点重复，请减少采样数或在更细的网格上绘制。	Sampling produced duplicate vertices. Reduce samples or use a finer mesh.
现有对应点格式无效。	Invalid existing correspondence format.
曲线路径模式无效。	Invalid curve path mode.
合并后超过 100 对对应点，请减少采样数或曲线数量。	Merged correspondences exceed 100 pairs. Reduce samples or curves.
曲线名称必须为 1–80 个字符。	Curve names must contain 1–80 characters.
曲线采样数为 2–30；闭合曲线至少 3 点。	Curve samples must be 2–30, or at least 3 for closed curves.
曲线控制节点	Curve control points
曲线节点间没有可用表面路径，可能跨越了断开的网格或排除区。	No usable surface path between curve points. The path may cross disconnected geometry or exclusions.
现有对应点重复。	Existing correspondences contain duplicates.
每侧曲线最多 32 个控制节点。	Up to 32 curve control points per side.
曲线节点重复；闭合曲线请勾选闭合，不要重复起点。	Duplicate curve points. For a closed curve, enable Closed instead of repeating the start point.
曲线采样与已有点对或其他曲线冲突，请检查方向、节点顺序或减少采样数。	Curve samples conflict with existing pairs or other curves. Check direction and control point order, or reduce samples.
曲线控制节点位于排除区域，请先恢复区域。	A curve control point is excluded. Restore the region first.
”两侧控制节点不足。	”: insufficient control points on one or both sides.
两侧控制节点不足。	: insufficient control points on one or both sides.
纹理细化参数格式无效。	Invalid texture refinement settings format.
纹理细化分辨率为 256/384/512，迭代 1–5 次，视图数为 1 或 3。	Texture refinement requires resolution 256/384/512, 1–5 iterations, and 1 or 3 views.
纹理细化强度为 1–100，最大位移为目标尺寸的 0.1%–10%。	Texture refinement strength must be 1–100 and maximum displacement 0.1%–10% of target size.
修复帧必须位于前后正常帧之间。	The repaired frame must lie between normal reference frames.
待修复几何无效。	Invalid geometry for repair.
全部模板顶点被约束锁定，无法重建异常结果。	All template vertices are constrained; the anomalous result cannot be rebuilt.
修复目标尺寸无效。	Invalid repair target dimensions.
插值与本帧约束会导致翻面，未采用修复。	Interpolation with this frame's constraints would flip faces. Repair rejected.
修复迭代或最大修正距离无效。	Invalid repair iterations or maximum correction distance.
插值附近的可信扫描面不足，未采用修复。	Insufficient reliable scan faces near the interpolation. Repair rejected.
修复违反软权重保护，未采用。	Repair violates soft weight protection and was rejected.
修复复检的可信表面覆盖不足。	Insufficient reliable surface coverage during repair validation.
修复参考帧顶点无效。	Invalid repair reference vertices.
修复软权重无效。	Invalid repair soft weights.
修复后的可信表面匹配不足，保留隔离。	Insufficient reliable surface matches after repair; remains isolated.
防翻面限制阻止修复，保留隔离。	Flip prevention blocked repair; remains isolated.
鼻尖	Nose Tip
鼻根	Nose Bridge
右眼外角	Right Outer Eye Corner
右眼内角	Right Inner Eye Corner
左眼内角	Left Inner Eye Corner
左眼外角	Left Outer Eye Corner
右眉外侧	Right Outer Brow
右眉内侧	Right Inner Brow
左眉内侧	Left Inner Brow
左眉外侧	Left Outer Brow
右鼻翼	Right Nose Wing
左鼻翼	Left Nose Wing
右嘴角	Right Mouth Corner
左嘴角	Left Mouth Corner
上唇中点	Upper Lip Center
下唇中点	Lower Lip Center
下巴	Chin
额头中点	Forehead Center
检测来自二维正面渲染并吸附到可见三角面顶点，请检查后采用；不是原生三维特征点预测。	Detected on frontal 2D renders and snapped to visible triangle vertices. Review before accepting; these are not native 3D landmark predictions.
检测截图格式无效。	Invalid detection snapshot format.
检测截图边长需为 128–1024 像素。	Detection snapshot dimensions must be 128–1024 pixels.
未检测到人脸	No face detected
检测到多个人脸	Multiple faces detected
人脸检测返回无效坐标。	Face detection returned invalid coordinates.
检测相机参数无效。	Invalid detection camera settings.
检测相机矩阵无效。	Invalid detection camera matrix.
检测相机投影无效。	Invalid detection camera projection.
检测相机射线无效。	Invalid detection camera ray.
二维特征点格式无效。	Invalid 2D landmark format.
超出画面	Outside the view
未命中可见表面	No visible surface hit
位于排除区域	In an excluded region
顶点吸附偏差过大	Vertex snapping error too large
吸附到重复顶点	Snapped to a duplicate vertex
自动检测请求无效。	Invalid automatic detection request.
缺少人脸模型，请在项目目录运行 python setup_landmarks.py。	Missing face model. Run python setup_landmarks.py in the project folder.
人脸模型校验失败，请运行 python setup_landmarks.py 重新获取。	Face model verification failed. Run python setup_landmarks.py to download it again.
，请将单个人脸调到正面并放大，或使用手动选点。	. Face a single mesh forward and zoom in, or select points manually.
人脸过小、偏转或倾斜较大，请放大并调到正面后重试。	Face too small, turned, or tilted. Zoom in and face it forward before retrying.
检测相机矩阵不可逆。	Detection camera matrix is not invertible.
只得到	Only obtained
对可用表面点，需要至少 6 对；请放大正面视图、检查排除区或手动选点。	usable surface pairs; at least 6 are needed. Zoom in on frontal views, check exclusions, or select manually.
自动对应点分布退化，请调整视角或手动选点。	Automatic point distribution is degenerate. Adjust the view or select points manually.
缺少 MediaPipe，请运行 python -m pip install -r requirements.txt。	Missing MediaPipe. Run python -m pip install -r requirements.txt.
诊断上限为 200,000 顶点、500,000 三角面。	Diagnostics are limited to 200,000 vertices and 500,000 triangles.
文件没有可显示的有限坐标顶点。	No displayable vertices with finite coordinates.
模型坐标跨度过大，请归一化后重试。	Mesh coordinate range is too large. Normalize and retry.
清理后没有有效三角面；无法生成可用模型。	No valid triangles remain after cleanup; cannot produce a usable mesh.
模型角色无效。	Invalid mesh role.
修复后 OBJ 超过 18 MB 上限。	Repaired OBJ exceeds 18 MB.
修复后仍有未解决的网格问题，未生成可应用结果。	Mesh issues remain after repair; no applicable result generated.
分离后超过该侧	After splitting, this side exceeds the
顶点上限，请先在建模软件中简化。	vertex limit. Simplify in a modeling application first.
无效或重复面	Invalid or duplicate face
无效 UV 引用；修复时保留几何	Invalid UV reference; repair retains geometry
无效 UV	Invalid UV
粗配准	Coarse Registration
中层贴合	Intermediate Fitting
全顶点精修	Full-vertex Refinement
纹理细化相机无效，请重置左侧视图。	Invalid texture refinement camera. Reset the left view.
纹理细化相机方向无效。	Invalid texture refinement camera direction.
纹理细化需要两侧都有完整 OBJ UV。	Texture refinement requires complete OBJ UVs on both meshes.
所有模板顶点均被锁定，无法纹理细化。	All template vertices are locked; texture refinement is unavailable.
法线夹角必须为 10–89 度。	Normal angle must be 10–89 degrees.
共同可见区域缺少可用纹理，请检查朝向、UV、透明区和纹理细节。	Shared visible regions lack usable texture. Check orientation, UVs, transparency, and texture detail.
没有找到可验证的纹理误差改善，未修改原结果。可尝试调整视角、降低强度或重新检查贴图。	No verified texture error improvement; original result unchanged. Adjust the view, reduce strength, or check textures.
缺少 OpenCV，请安装 requirements.txt 后重启服务。	Missing OpenCV. Install requirements.txt and restart the service.
纹理视图栅格化开销过高，请降低分辨率或先清理重叠网格。	Texture view rasterization is too expensive. Reduce resolution or clean overlapping geometry.
纹理细化软权重无效。	Invalid texture refinement soft weights.
可靠光流对应不足，未修改结果；请检查是否同一人物、贴图是否相似以及左侧朝向。	Insufficient reliable optical flow matches; result unchanged. Check identity, texture similarity, and left view direction.
不是支持的 Mesh Wave 工程文件（版本 1）。	Not a supported Mesh Wave project file (version 1).
工程缺少模型信息。	Project is missing mesh information.
工程至少需要一个模型。	A project needs at least one mesh.
工程点对格式无效。	Invalid project correspondence format.
工程排除区域格式无效。	Invalid project exclusion format.
曲线生成点记录与现有点对不一致。	Curve-generated records do not match existing pairs.
待配对点	Pending correspondence
工程参数格式无效。	Invalid project settings format.
工程贴合参数超出范围。	Project fitting settings are out of range.
工程法线夹角必须为 10–89 度。	Project normal angle must be 10–89 degrees.
工程求解模式无效。	Invalid project solver mode.
工程烘焙参数无效。	Invalid project baking settings.
工程烘焙参数超出范围。	Project baking settings are out of range.
工程模型内容或名称无效。	Invalid project mesh content or name.
工程模型超过大小限制。	Project mesh exceeds the size limit.
工程包含重复对应点。	Project contains duplicate correspondences.
待配对点与现有点对或排除区域冲突。	Pending point conflicts with existing correspondences or exclusions.
工程贴合结果缺少模型或完整点对。	Project fitted result is missing meshes or complete correspondences.
工程结果顶点数量或坐标无效。	Invalid project result vertex count or coordinates.
手动修正标记无效。	Invalid manual edit flag.
纹理细化结果标记无效。	Invalid texture refinement flag.
带贴图的模型需要完整 UV。	Textured meshes need complete UVs.
排除面	Excluded faces
带烘焙贴图的结果需要模板 UV。	Baked results require template UVs.
仅允许同源请求。	Only same-origin requests are allowed.
请求大小上限为 96 MB。	Request size limit is 96 MB.
计算失败，请检查模型或查看本地服务日志。	Computation failed. Check the mesh or local service logs.
正在计算，请稍后重试。	Computation in progress. Try again later.
接口不存在。	Endpoint not found.
目标参与贴合的区域没有有效三角面。	No valid triangles in the target fitting region.
模板包含零面积或过小三角面，请先清理模型。	Template has zero-area or tiny triangles. Clean the mesh first.
时序平滑参数无效。	Invalid temporal smoothing settings.
时序平滑强度为 1–90，最大修正距离为目标尺寸的 0.1%–5%。	Temporal strength must be 1–90 and max correction 0.1%–5% of target size.
时序模式必须为单向或双向。	Temporal mode must be forward or bidirectional.
自适应开关必须为布尔值，速度阈值为目标尺寸的 0.1%–10% / 帧。	Adaptive mode must be boolean; speed threshold must be 0.1%–10% of target size per frame.
异常检测开关必须为布尔值，异常阈值为 0.1%–20%。	Anomaly detection must be boolean and threshold 0.1%–20%.
异常修复需要开启检测，连续修复上限为 1–5 帧。	Anomaly repair requires detection; maximum consecutive repairs must be 1–5 frames.
上一帧模板顶点无效。	Invalid previous frame template vertices.
上一帧速度参考无效。	Invalid previous frame speed reference.
下一帧模板顶点无效。	Invalid next frame template vertices.
PNG 贴图超过允许大小，请降低图片分辨率。	PNG texture exceeds the size limit. Reduce image resolution.
贴图名称或内容无效。	Invalid texture name or content.
贴图超过大小限制。	Texture exceeds the size limit.
仅支持 PNG 或 JPEG 贴图。	Only PNG or JPEG textures are supported.
模板需要每个面角都有有效 UV。	Every template face corner needs a valid UV.
模板 UV 需位于单张 0–1 空间；暂不支持 UDIM。	Template UVs must fit a single 0–1 tile. UDIM is not supported.
贴合结果顶点无效或模板过大。	Invalid fitted vertices or template too large.
贴图分辨率仅支持 256、512、1024、2048。	Texture resolution must be 256, 512, 1024, or 2048.
边缘扩展范围为 0–16 像素。	Edge padding must be 0–16 pixels.
最大投射距离需为目标包围盒对角线的 0.1%–20%。	Max projection distance must be 0.1%–20% of the target bounding-box diagonal.
扫描模型需要每个面角都有有效 UV。	Every scan face corner needs a valid UV.
排除区域格式无效。	Invalid exclusion format.
扫描模型尺寸无效。	Invalid scan dimensions.
模板没有可烘焙的 UV 像素，请检查 UV、排除区域或分辨率。	No bakeable template UV pixels. Check UVs, exclusions, or resolution.
没有像素通过投射距离和法线检查，请检查贴合结果、面朝向或增大投射距离。	No pixels passed distance and normal checks. Check the fit, face orientation, or increase projection distance.
纹理模型导出需要完整 UV。	Textured mesh export requires complete UVs.
贴图文件损坏或无法读取。	Texture file is damaged or unreadable.
UV 布局的栅格化开销过高，请降低分辨率或整理 UV。	UV rasterization is too expensive. Reduce resolution or clean the UV layout.
模板 UV 存在重叠像素，请先展开为不重叠的单张 UV。	Template UV pixels overlap. Unwrap to a single non-overlapping tile first.
贴图只支持 PNG/JPEG，最多 16 百万像素。	Textures must be PNG/JPEG, up to 16 million pixels.
需要至少三个有限坐标的 OBJ 顶点。	At least three OBJ vertices with finite coordinates are required.
需要有效的多边形面；不支持只有点云的 OBJ。	Valid polygon faces are required; point-cloud-only OBJ files are unsupported.
首版上限为 200,000 顶点、500,000 三角面。	Input limit is 200,000 vertices and 500,000 triangles.
导出顶点数量或坐标无效。	Invalid export vertex count or coordinates.
对应点不能重合或位于同一直线上，请分散选择。	Correspondences must not coincide or be collinear. Spread them across the mesh.
对应点产生了无效的尺度。	Correspondences produced an invalid scale.
模板上限为 100,000 顶点；请先简化模板。	Template limit is 100,000 vertices. Simplify it first.
求解模式无效。	Invalid solver mode.
超过 25,000 顶点的模板请使用多阶段求解。	Use multi-stage solving for templates above 25,000 vertices.
请选取 3–100 对对应点，建议至少 6 对。	Select 3–100 correspondence pairs; at least 6 are recommended.
对应点必须使用整数顶点索引。	Correspondences must use integer vertex indices.
对应点超出模型范围。	Correspondence indices are outside the mesh range.
每个顶点只能用于一组对应点。	Each vertex can be used in only one correspondence pair.
迭代次数或平滑参数超出范围。	Iterations or smoothing settings are out of range.
目标模型尺寸为零。	Target mesh has zero size.
对应点与固定区域约束会导致翻面或严重压扁，请重选对应点或缩小排除区域。	Correspondences and fixed regions would cause flips or severe collapse. Reselect pairs or reduce exclusions.
两侧表面法线方向大多相反，请先在建模软件中统一面朝向。	Most surface normals face opposite directions. Align face orientations in a modeling application first.
OBJ UV 坐标或索引无效。	Invalid OBJ UV coordinates or indices.
索引无效。	Invalid index.
排除区域包含对应点，请先移动或删除冲突的点对。	Exclusions contain correspondence points. Move or delete conflicting pairs first.
OBJ 顶点必须包含 x、y、z。	OBJ vertices must contain x, y, and z.
法线匹配不足，请检查两侧面的朝向是否一致，或适当增大法线夹角。	Insufficient normal-compatible matches. Check face orientations or increase the normal angle.
OBJ UV 必须包含 u、v。	OBJ UVs must contain u and v.
求解失败；请检查模型和对应点。	Solving failed. Check meshes and correspondences.
OBJ 面索引无效。	Invalid OBJ face index.
OBJ UV 索引无效。	Invalid OBJ UV index.
`.trim().split('\n').map(line=>line.split('\t'));
