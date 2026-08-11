# Terraform

[ Introduction · 《Terraform入门教程》  https://lonegunmanb.github.io/introduction-terraform/](https://lonegunmanb.github.io/introduction-terraform/ " Introduction · 《Terraform入门教程》  https://lonegunmanb.github.io/introduction-terraform/")

Terraform的核心概念是“资源”和“提供者”。资源代表基础设施中的一项资源，如计算、存储、网络等，而提供者则是由云服务提供商进行开发的插件。阿里云作为国内第一家与Terraform集成的厂商、社区非常活跃的“提供者”之一，为用户提供了通过Terraform管理阿里云资源的能力。

![](image/CAEQSRiBgMCXlffF1BgiIGMxMTA5ODYxNzZhMzQyOGY5NTIyOD.svg)

- 基础设施即代码：通过Terraform，可以将基础设施的定义和配置存储为代码，这样可以进行版本控制、团队协作和复用，减少了手动操作和错误的同时，提高了效率。
- 可靠性和稳定性：阿里云技术团队提供了场景级自动化用例测试保障、自动对接平台化等内部保障能力。让用户使用过程中平稳、顺滑、可靠。
- 丰富的资源支持：阿里云坚持面向资源化理念提供服务，在Terraform资源定义标准化、支持度和支持效率方面持续投入。为用户提供“开箱即用”的使用体验。
- 声明式语言：Terraform使用HCL（HashiCorp Configuration Language）作为配置语言，它是一种声明式的语言，通过描述期望的状态，而不是编写详细的步骤，使得代码更易于理解和维护。
- 可扩展性：Terraform提供了丰富的资源和提供者插件，可以满足不同的需求，并且用户也可以自定义和扩展插件来支持特定的基础设施。
- 与其他工具的集成：Terraform可以与其他工具（如Ansible、Jenkins、GitLab等）集成，实现更复杂的自动化工作流程，如自动化测试、持续集成和持续部署等。
