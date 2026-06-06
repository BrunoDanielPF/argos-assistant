from pathlib import Path
import re


def run(arguments: dict) -> dict:
    name = arguments["name"]
    directory = Path(arguments["directory"]).expanduser()
    java_version = arguments["java_version"]
    build_tool = arguments["build_tool"]
    group_id = arguments["group_id"]

    project = directory / name
    if project.exists() and any(project.iterdir()):
        raise FileExistsError(f"destination is not empty: {project}")
    project.mkdir(parents=True, exist_ok=True)

    artifact_package = re.sub(r"[^a-zA-Z0-9]", "", name)
    class_name = "".join(part.capitalize() for part in re.split(r"[-_]+", name))
    package_name = f"{group_id}.{artifact_package.lower()}"
    package_path = Path(*package_name.split("."))

    files = {
        "src/main/resources/application.properties": (
            f"spring.application.name={name}\n"
        ),
        ".gitignore": ".gradle/\ntarget/\nbuild/\n.idea/\n*.iml\n",
        str(
            Path("src/main/java")
            / package_path
            / f"{class_name}Application.java"
        ): _application_java(package_name, class_name),
        str(
            Path("src/test/java")
            / package_path
            / f"{class_name}ApplicationTests.java"
        ): _test_java(package_name, class_name),
    }
    if build_tool == "maven":
        files["pom.xml"] = _pom_xml(group_id, name, java_version)
    else:
        files["settings.gradle"] = f"rootProject.name = '{name}'\n"
        files["build.gradle"] = _gradle_build(group_id, java_version)

    created = []
    for relative_path, content in files.items():
        target = project / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created.append(str(target))
    return {"project_path": str(project), "created_files": sorted(created)}


def _application_java(package_name: str, class_name: str) -> str:
    return (
        f"package {package_name};\n\n"
        "import org.springframework.boot.SpringApplication;\n"
        "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
        "@SpringBootApplication\n"
        f"public class {class_name}Application {{\n"
        "    public static void main(String[] args) {\n"
        f"        SpringApplication.run({class_name}Application.class, args);\n"
        "    }\n"
        "}\n"
    )


def _test_java(package_name: str, class_name: str) -> str:
    return (
        f"package {package_name};\n\n"
        "import org.junit.jupiter.api.Test;\n"
        "import org.springframework.boot.test.context.SpringBootTest;\n\n"
        "@SpringBootTest\n"
        f"class {class_name}ApplicationTests {{\n"
        "    @Test\n"
        "    void contextLoads() {}\n"
        "}\n"
    )


def _pom_xml(group_id: str, artifact_id: str, java_version: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
  </parent>
  <groupId>{group_id}</groupId>
  <artifactId>{artifact_id}</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>{java_version}</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""


def _gradle_build(group_id: str, java_version: int) -> str:
    return f"""plugins {{
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}}

group = '{group_id}'
version = '0.0.1-SNAPSHOT'

java {{
    toolchain {{
        languageVersion = JavaLanguageVersion.of({java_version})
    }}
}}

repositories {{
    mavenCentral()
}}

dependencies {{
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}}

tasks.named('test') {{
    useJUnitPlatform()
}}
"""
