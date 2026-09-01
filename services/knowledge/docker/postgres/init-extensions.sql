-- 启用 pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用 zhparser
CREATE EXTENSION IF NOT EXISTS zhparser;

-- 创建中文搜索配置
CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser);

-- 把所有词性都映射成 simple 字典(可被检索的词)
ALTER TEXT SEARCH CONFIGURATION chinese_zh ADD MAPPING FOR n,v,a,i,e,l,j WITH simple;