# Spring Boot 请求链路与 IoC / DI 笔记

这份文档关注 Spring Boot 服务中一次请求如何从 HTTP 边界进入业务层，再访问数据库，以及 IoC、DI、Bean 为什么能减少对象创建和实现细节之间的耦合。测试问题如果出现 Controller、Service、Repository、Bean、依赖注入或事务边界，应该优先命中本篇。

## 典型请求链路

一个常见 Spring Boot 请求链路可以写成：

`HTTP Request → Controller → Service → Repository / DAO → DB`

Controller 负责处理 HTTP 请求、参数、基础校验和响应，不应该塞入大量业务流程。Service 负责真正的业务逻辑和流程编排，也是常见的事务边界。Repository / DAO 专注数据库访问，例如查询、插入和更新，不负责决定一整个业务动作应该如何组合。

一句话可以记成：Controller 管 HTTP，Service 管业务和事务，DAO 管数据库。

## Service 为什么负责业务编排

例如修改商品信息时，业务可能需要先更新数据库，再删除 Redis 缓存，必要时还要发送一条 MQ 事件。合理结构更接近：

`Controller → ProductService → DAO 更新数据库 → 删除 Redis 缓存 → 发送 MQ → 返回结果`

Redis 和 MQ 都是业务流程依赖的外部能力，不建议直接塞进 DAO。DAO 如果同时负责数据库、缓存和消息发送，数据访问层就会和业务规则混在一起，后续测试、维护和替换实现都会变得困难。

## IoC、DI 与 Bean

IoC 是 Inversion of Control，控制反转。它表示对象的创建和生命周期不再由业务代码到处自己管理，而是交给 Spring 容器。

DI 是 Dependency Injection，依赖注入。一个类需要另一个对象时，不再主动 `new` 出具体实现，而是声明自己的依赖，由 Spring 把合适的对象实例注入进来。

Bean 是被 Spring 容器创建和管理的对象实例。`@Controller`、`@Service`、`@Repository` 等组件通常都会注册成 Bean。默认情况下，Spring Bean 的常见作用域是 singleton，也就是同一个 Spring 容器里通常复用同一个实例；当然 Spring 也支持 prototype 等其他作用域。

最短口述版是：IoC 是“对象交给 Spring 管”，DI 是“Spring 把依赖给你”，Bean 是“被 Spring 管理的对象实例”。

## 分层不等于 IoC / DI

把代码拆成 Controller、Service、DAO，只解决了结构分层。如果 Controller 里依然写：

```java
new ProductServiceImpl()
```

那么 Controller 仍然知道具体实现类，也负责对象创建。这样上层代码和实现细节绑得很紧。

IoC / DI 再向前一步：Controller 只声明“我需要 ProductService”，Spring 决定创建哪个实现，并把它注入进来。这里的解耦并不是完全没有依赖，而是让上层依赖能力或接口，而不是依赖具体实现对象的创建方式。

## 接口与实现

典型关系可以表示为：

`Controller → ProductService（接口） → ProductServiceImpl（实现，由 Spring 创建）`

Controller 面向接口使用能力，Spring 负责把实现注入进去。这样测试时可以替换 mock，实现变化时也不一定需要修改上层调用代码。

## 事务通常放在哪里

一个 Service 方法如果需要连续调用多个 DAO 完成同一业务动作，通常会在 Service 层使用 `@Transactional`。原因是 Service 知道这几个数据库操作是不是必须一起成功。把事务随意拆到不同 DAO 上，容易让业务边界破碎，出现部分操作提交、部分操作失败的情况。

完整面试表达可以是：Spring Boot 中，请求通常从 Controller 进入，由 Service 处理业务逻辑并编排 Redis、MQ 或数据库操作，再由 Repository / DAO 访问数据。Spring 通过 IoC 和 DI 管理这些对象之间的依赖，业务代码不需要到处自己 new 对象，Controller 通常只依赖 Service 接口，具体实现交给 Spring 提供。
