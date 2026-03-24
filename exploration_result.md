# 字段勘探结果（首版）

生成时间：2026-03-24（UTC）

> 说明：当前运行环境对 `api.xiaoyuzhoufm.com` 的直连返回 403 隧道错误，在线勘探无法完成。
> 本结果基于公开项目 `ultrazg/xyz` 的接口说明文档样例抽取而成，可作为首版字段字典。

## 频道级候选字段

- podcast.id / pid
- podcast.title
- podcast.description
- podcast.language
- podcast.category
- podcast.episodeCount
- podcast.subscriberCount
- podcast.playCount（可能并非所有频道都返回）
- podcast.commentCount（可能需从单集汇总）
- podcast.podcasters[].nickname

## 单集级候选字段

- episode.eid / id
- episode.title
- episode.pubDate
- episode.duration
- episode.commentCount
- episode.playCount（可用性待线上验证）
- episode.shownotes / description

## 评论级候选字段

- comment.id
- comment.text
- comment.createdAt
- comment.likeCount
- comment.replyCount

## 当前结论

1. 你的核心目标字段中，“内容数量（episodeCount）”和“评论数量（至少单集 commentCount）”具备较高可行性。
2. “观看量/播放量（playCount）”存在端差异与版本差异，建议在你本地网络环境和登录态下优先验证。
3. 已提供脚本 `discover.py`，在你可直连网络环境中可自动生成真实字段覆盖率报告。
