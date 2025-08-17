# New-Item -Path . -Name ".venv.ps1" -ItemType "file" -Value @" 

'''
这段 PowerShell 代码的作用是创建一个新的文件。下面是对这段代码的详细解释：

New-Item：这是一个 PowerShell cmdlet，用于创建新的项目，比如文件、目录、符号链接等。

-Path .：这个参数指定了新项目创建的路径。这里的 . 表示当前目录。

-Name ".venv.ps1"：这个参数指定了新文件的名称。在这里，文件名是 .venv.ps1。

-ItemType "file"：这个参数指定了新项目的类型。在这里，类型是 file，表示要创建一个文件。

-Value @"：这个参数用于指定新文件的内容。在这里，@"" 表示文件内容为空。注意，@"" 是一个 Here-String，用于定义多行字符串。

总的来说，这段代码的作用是在当前目录下创建一个名为 .venv.ps1 的空文件。这个文件可能用于后续的虚拟环境管理或其他脚本执行。
'''
if (Test-Path -Path ".venv") {
    .\.venv\Scripts\Activate.ps1
}
# else {
#     # 创建新虚拟环境（可选）
#     python -m venv .venv
    
#     # 激活新环境
#     .\.venv\Scripts\Activate.ps1
    
#     # 安装依赖（可选）
#     if (Test-Path -Path "requirements.txt") {
#         pip install -r requirements.txt
#     }
# }
# "@
