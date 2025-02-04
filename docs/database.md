# 版本
20250115: v0

# 用户数据
## 添加用户(前端不需要，用户登录后，后台调用入库操作)
```
url: "http://localhost:8000/add_user"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "user_name": "tester", //微信名
    ...
}
```
## 查询用户信息
```
url: "http://localhost:8000/query_user_info"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "user_name": "tester", //微信名
    "phone": "1234567890", //手机号
    "email": "123@qq.com", //邮箱
}
```
# 会话数据

## 删除
### 删除单一会话
```
url: "http://localhost:8000/delete_specific_session"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "session_id": "abc", //会话id
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "ok": 0, //0表示成功，非0表示失败
    "failed": "" //空表示成功，否则是出错信息
}
```
### 清空所有会话
```
url: "http://localhost:8000/delete_sessions"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "ok": 0, //0表示成功，非0表示失败
    "failed": "" //空表示成功，否则是出错信息
}
```
## 查询
### 查询会话历史
```
url: "http://localhost:8000/query_session_names"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "ok": 0, //0表示成功，非0表示失败
    "failed": "" //空表示成功，否则是出错信息
    "sessions": [
        {
            "session_id": "abc", //会话id
            "session_title": "abc", //会话title
        }
        ...
    ]
}
```
### 查询单一会话
```
url: "http://localhost:8000/query_session_info"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "session_id": "123", //会话id
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "session_id": "123", //会话id
    "ok": 0, //0表示成功，非0表示失败
    "failed": "" //空表示成功，否则是出错信息
    "chats": [
        {
            "role": "user"
            "msg": "帮我讲个笑话"
        },
        {
            "role": "ai"
            "msg": "有一天，小明去面试，面试官问他..."
        },
        ...
    ]
}
```
## 插入
### 插入单一会话内部-用户输入
```
url: "http://localhost:8000/add_chat"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "role": "user", //会话角色
    "msg": "今天天气不错" //用户输入内容
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "ok": 0, //0表示成功，非0表示失败
    "failed": "" //空表示成功，否则是出错信息
}
```
### 插入单一会话内部-AI回复（这个前端可能不需要，后台在ai回复调用完后插入）
```
url: "http://localhost:8000/add_chat"
method: "POST"
content-type: "application/json"
request parameters:
{
    "request_id": "uuxx", //请求id
    "user_id": "123", //微信用户id
    "role": "ai", //会话角色
    "msg": "是的，请问有什么可以帮到您" //ai回复内容
}
response parameters:
{
    "request_id": "uuxx", //请求id
    "ok": 0, //0表示成功，非0表示失败
    "failed": "" //空表示成功，否则是出错信息
}
```