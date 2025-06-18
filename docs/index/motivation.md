
# Motivation

While working on AI-related projects in Python, I was looking for a dependency injection (DI) framework. After evaluating existing options, my impression was that the most either lacked key features — such as integrated AOP — or had APIs that felt overly technical and complex, which made me develop a library on my own with the following goals

- bring both di and AOP features together in a lightweight library,
- be as minimal invasive as possible,
- offering mechanisms to easily extend and customize features without touching the core,
- while still offering a _simple_ and _readable_ api that doesnt overwhelm developers

Especially the AOP integration definitely makes sense, as aspects on their own also usually require a context, which in a DI world is simply injected.
