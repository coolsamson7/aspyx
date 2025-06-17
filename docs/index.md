# Introduction

Aspyx is a lightweight Python library that provides both Dependency Injection (DI) and Aspect-Oriented Programming (AOP) support.

The following DI features are supported

* constructor and setter injection
* injection of configuration variables
* possibility to define custom injections
* post processors
* support for factory classes and methods
* support for eager and lazy construction
* support for scopes singleton, request and thread
* possibilty to add custom scopes
* conditional registration of classes and factories ( aka profiles in spring )
* lifecycle events methods `on_init`, `on_destroy`, `on_running`
* bundling of injectable objects according to their module location including recursive imports and inheritance
* instantiation of - possibly multiple - container instances - so called environments - that manage the lifecycle of related objects
* hierarchical environments

With respect to AOP:

* support for before, around, after and error aspects 
* sync and async method support

The library is thread-safe and heavily performance optimized as most of the runtime information is precomputed and cached!

