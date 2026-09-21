::ILANG
[TYPE:agent-guide][PROJECT:brand-deal-radar][LANG:zh]
::OBJECTIVE{维护面向美区的旅行装备与服务优惠静态站}
::RULE{.ilang/site.ilang 是品牌、域名、厂商和来源的唯一配置入口}
::RULE{只从公开官方来源取数据，遵守 robots.txt；不绕登录、反爬或付费墙}
::RULE{只展示有可核对来源的优惠；价格与截止日期缺失时省略字段}
::RULE{过期优惠必须标过期或下架；社交发布必须先人工核实}
::BOUNDARY{never:编优惠|编价格|编佣金|编截止日期|伪造验证结果}
::ACTION{允许:修改配置|修抓取器|运行测试|生成静态站|按授权发布}
