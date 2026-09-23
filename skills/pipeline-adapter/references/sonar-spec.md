# sonar-project.properties 规范速查

## 通用必填字段
```properties
sonar.projectKey=demo/go-demo
sonar.projectName=go-demo
sonar.projectVersion=1.0
sonar.sources=.
sonar.sourceEncoding=UTF-8
```

## 各技术栈差异

### Go
```properties
sonar.exclusions=**/*_test.go,**/vendor/**,**/build.py,**/devops_api.py,**/test_build.py
sonar.tests=.
sonar.test.inclusions=**/*_test.go
sonar.test.exclusions=**/vendor/**
sonar.go.coverage.reportPaths=./cov.out
# 以下字段为可选，如有测试报告输出可填写
# sonar.go.tests.reportPaths=./test-report.json
```

### Java
```properties
sonar.language=java
sonar.sources=log/src/main,helloworld/src/main
sonar.java.binaries=log/target/classes,helloworld/target/classes
sonar.exclusions=**/build.py,**/devops_api.py,**/test_build.py
sonar.tests=log/src/test,helloworld/src/test
sonar.coverage.jacoco.xmlReportPaths=log/target/coverage-reports/jacoco.xml
sonar.junit.reportPaths=log/target/surefire-reports/
sonar.java.coveragePlugin=sonar-jacoco
```

### C/C++
```properties
sonar.language=c++
sonar.cxx.coverage.reportPath=reports/coverage.xml
sonar.exclusions=**/CMakeFiles/**,**/build.py,**/devops_api.py,**/test_build.py
```

### Web（前端）
```properties
sonar.sources=src
sonar.exclusions=**/build.py,**/devops_api.py,**/test_build.py
sonar.coverage.exclusions=src/*.js
sonar.tests=tests
sonar.javascript.lcov.reportPaths=coverage/lcov.info
sonar.testExecutionReportPaths=coverage/ut-report.xml
sonar.eslint.reportPaths=eslint-report.json
```

### Python
```properties
sonar.sources=.
sonar.exclusions=**/build.py,**/devops_api.py,**/test_build.py
```

## 注意事项
- `sonar.login` 字段在原规范中存在示例 token，实际使用中流水线已内置，无需硬编码到 properties 文件中。
- 非代码类文件（doc、lib、中文命名文件）需加入 `sonar.exclusions`。
