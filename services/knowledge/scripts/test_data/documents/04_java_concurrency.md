# Java 并发入门

这份文档专门用于拉开 Java 并发主题和 Python RAG 后端主题的距离。它覆盖 Thread、synchronized、volatile、ExecutorService、CompletableFuture 和死锁排查。这样当测试问题询问 Java 多线程时，检索系统应该命中这份文档，而不是只能返回 Python 简介。

## Thread 与 Runnable

Java 中可以直接创建 Thread，也可以把任务写成 Runnable 或 Callable 交给线程执行。直接 new Thread 适合演示概念，但服务端程序通常不应该为每个请求随意创建新线程。线程创建和上下文切换都有成本，数量失控会让 CPU 花大量时间调度，甚至导致内存耗尽。实际项目更常用线程池统一管理并发任务。

## synchronized 与 Lock

synchronized 可以保护临界区，保证同一时刻只有一个线程进入被保护的代码块。它还能建立 happens-before 关系，让一个线程释放锁前的写入对后续获得同一把锁的线程可见。ReentrantLock 提供了更灵活的能力，例如可中断获取锁、尝试获取锁和公平锁。选择哪一种，取决于代码是否需要这些额外控制。

## volatile 的边界

volatile 主要解决可见性和禁止特定指令重排序的问题。一个线程修改 volatile 变量后，其他线程能更快看到新值。它适合做状态标记，例如 shutdown flag。但 volatile 不能让复合操作自动具备原子性，count++ 仍然可能在并发下丢失更新。计数器通常应该使用 AtomicInteger、LongAdder 或锁。

## ExecutorService 与线程池

ExecutorService 把任务提交和线程管理分离。开发者提交 Runnable 或 Callable，线程池负责复用工作线程、排队任务和控制并发度。固定大小线程池适合 CPU 或外部资源明确的场景，缓存线程池适合短任务但要警惕数量膨胀。服务关闭时应该调用 shutdown 或 shutdownNow，并处理未完成任务。

## CompletableFuture

CompletableFuture 适合表达异步任务的组合关系，例如 thenApply、thenCompose、allOf 和 exceptionally。它能让多个远程调用并行执行，再把结果合并。使用时要注意默认线程池和阻塞操作，如果在公共 ForkJoinPool 里执行大量阻塞 IO，可能拖慢其他异步任务。复杂链路最好显式传入业务线程池。

## 死锁与排查

死锁通常发生在多个线程以不同顺序持有锁并等待对方释放。排查时可以使用 jstack、线程 dump 或监控工具查看 BLOCKED 状态和锁等待关系。预防手段包括固定加锁顺序、缩小锁范围、避免在持锁时调用外部服务，以及使用 tryLock 设置超时。并发 bug 往往具有偶现性，测试需要重复运行和增加日志。
