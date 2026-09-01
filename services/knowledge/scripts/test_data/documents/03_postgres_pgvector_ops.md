# PostgreSQL pgvector 运维笔记

这份文档用于测试数据库和向量索引相关问题。它覆盖 pgvector 字段、HALFVEC、索引类型、查询模式、迁移和性能观察。问题里如果出现 HNSW、IVFFlat、cosine distance、向量维度或连接池，应该更容易命中这里，而不是命中 FastAPI 请求流程或 Java 并发资料。

## 向量字段与维度

pgvector 会把 embedding 存成 vector、halfvec 或 sparsevec 等类型。练习项目里使用 HALFVEC 可以减少存储空间，但字段维度必须和 embedding 模型输出维度一致。例如模型输出 1536 维，数据库列也要声明为 1536 维。维度不一致时，插入会失败，或者查询距离计算无法执行。换模型、改 output_dimensionality 后，表结构和历史数据都需要一起考虑。

## 余弦距离查询

常见查询写法是把用户问题先转成 query embedding，再按 cosine_distance 排序取 top-k。余弦距离越小代表方向越接近。SQLAlchemy 配合 pgvector 时，可以在 order_by 中调用 Chunk.embedding.cosine_distance(query_vector)。为了让日志更容易读，测试时应该打印 document_id、chunk_index 和内容 preview，这样可以确认返回结果是否都来自同一份重复文档。

## HNSW 与 IVFFlat

HNSW 索引适合高召回、低延迟的近似搜索，构建时会占用更多内存，写入也可能更重。IVFFlat 需要先有一定数据量再建索引，并且查询时通常要调 probes，在速度和召回之间取舍。小型练习库即使没有索引也能跑通，因为全表排序的成本不高；当 chunk 数量上万后，索引、过滤条件和数据库参数才会明显影响体验。

## 元数据过滤

向量搜索不一定只靠相似度。实际系统经常先按租户、文档类型、项目、权限或更新时间过滤，再在候选范围内做向量排序。这样可以避免用户检索到无权限文档，也能减少无关主题干扰。练习项目目前只按全库相似度排序，适合验证最小链路；后续可以在 Chunk 或 Document 上补充 metadata 字段，再把过滤条件加入查询。

## 表结构、扩展与迁移

PostgreSQL 使用 pgvector 前要安装扩展，通常需要执行 create extension vector。SQLAlchemy 的 Base.metadata.create_all 适合练习和本地初始化，但生产系统更常用迁移工具管理表结构。增加索引、修改向量维度、增加 metadata 列，都应该通过可重复的迁移脚本完成。否则本地、测试环境和线上环境很容易出现表结构不一致。

## 运行时观察

检索服务上线后，需要观察数据库连接数、慢查询、索引命中、磁盘增长和 embedding 写入失败率。重复运行测试入库脚本会产生同名文档和重复 chunks，top-k 可能全部返回同一段内容的多个副本。测试数据脚本最好在入库前清理自己管理的样例文档，避免误把重复数据问题当成向量检索问题。
