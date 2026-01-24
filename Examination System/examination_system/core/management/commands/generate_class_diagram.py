"""
Django management command to generate class diagrams from models.
Usage: python manage.py generate_class_diagram
"""

from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models
from pathlib import Path
import sys


class ModelAnalyzer:
    """Analyzes Django models and generates class diagram code."""
    
    TYPE_MAPPING = {
        'CharField': 'String',
        'TextField': 'String',
        'IntegerField': 'Integer',
        'PositiveIntegerField': 'Integer',
        'BigIntegerField': 'Long',
        'DecimalField': 'Decimal',
        'FloatField': 'Decimal',
        'BooleanField': 'Boolean',
        'DateTimeField': 'DateTime',
        'DateField': 'DateTime',
        'EmailField': 'String',
        'ImageField': 'String',
        'FileField': 'String',
        'JSONField': 'String',
    }
    
    def __init__(self):
        self.models = {}
        self.enums = {}
        
    def get_field_type(self, field):
        """Get UML type for a Django field."""
        field_type_name = field.__class__.__name__
        
        if field_type_name in self.TYPE_MAPPING:
            return self.TYPE_MAPPING[field_type_name]
        
        if isinstance(field, (models.ForeignKey, models.ManyToManyField, models.OneToOneField)):
            return 'Long'
        
        return 'String'
    
    def analyze_model(self, model):
        """Analyze a Django model and extract its structure."""
        model_name = model.__name__
        
        if model_name in self.models:
            return
        
        # Essential fields only
        essential_fields = ['id', 'name', 'title', 'code', 'text', 'content', 'body', 'message',
                          'status', 'email', 'username', 'full_name', 'role',
                          'start_time', 'duration_minutes', 'total_mark', 'pass_mark',
                          'score', 'is_active', 'camera_enabled', 'microphone_enabled',
                          'suspicious', 'is_read', 'platform_name', 'two_factor_email']
        
        attributes = []
        for field in model._meta.get_fields():
            if field.name == 'id' or field.name not in essential_fields:
                continue
            
            if isinstance(field, models.ManyToManyField):
                continue
            
            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                field_type = 'Long'
                field_name = f"{field.name}_id"
            else:
                field_type = self.get_field_type(field)
                field_name = field.name
            
            attributes.append({
                'name': field_name,
                'type': field_type,
            })
        
        methods = []
        if hasattr(model, '__str__'):
            methods.append({
                'name': '__str__()',
                'return_type': 'String',
            })
        
        if hasattr(model, 'load'):
            methods.append({
                'name': '{static} load()',
                'return_type': model_name,
            })
        
        self.models[model_name] = {
            'attributes': attributes,
            'methods': methods,
        }
        
        # Extract enums (avoid name collisions like multiple inner classes named Status)
        for attr_name in dir(model):
            attr = getattr(model, attr_name, None)
            if isinstance(attr, type) and issubclass(attr, models.TextChoices):
                enum_values = [choice[0] for choice in attr.choices]
                enum_key = f"{model_name}{attr_name}"
                self.enums[enum_key] = enum_values
    
    def generate_plantuml(self):
        """Generate PlantUML class diagram code."""
        output = []
        output.append("@startuml Examination System - Class Diagram\n")
        output.append("!theme plain\n")
        output.append("skinparam roundcorner 10\n")
        output.append("skinparam shadowing true\n")
        output.append("skinparam linetype ortho\n\n")
        
        output.append("skinparam class {\n")
        output.append("    BackgroundColor<<UserManagement>> #E3F2FD\n")
        output.append("    BackgroundColor<<AcademicManagement>> #F1F8E9\n")
        output.append("    BackgroundColor<<ExamManagement>> #FFF3E0\n")
        output.append("    BackgroundColor<<Proctoring>> #FCE4EC\n")
        output.append("    BackgroundColor<<Communication>> #E8EAF6\n")
        output.append("    BackgroundColor<<System>> #F5F5F5\n")
        output.append("    BorderColor #1976D2\n")
        output.append("    ArrowColor #1976D2\n")
        output.append("    TitleFontSize 13\n")
        output.append("    TitleFontStyle bold\n")
        output.append("    FontSize 11\n")
        output.append("}\n\n")
        
        if self.enums:
            output.append("package \"Enumerations\" {\n")
            for enum_name, enum_values in self.enums.items():
                output.append(f"    enum {enum_name} {{\n")
                for value in enum_values:
                    output.append(f"        {value}\n")
                output.append("    }\n\n")
            output.append("}\n\n")
        
        packages = {
            'User Management': ['User', 'TeacherNotificationSettings'],
            'Academic Management': ['Subject', 'Group', 'Question', 'QuestionChoice'],
            'Exam Management': ['Exam', 'ExamQuestion', 'StudentExam', 'StudentAnswer', 'ExamEvent', 'ExamNotification'],
            'Proctoring System': ['ProctorSession', 'ProctorSnapshot', 'ProctorAudioStream'],
            'Communication System': ['Message', 'GroupMessage', 'StudentJoinRequest'],
            'System Configuration': ['SystemSettings']
        }
        
        package_stereotypes = {
            'User Management': '<<UserManagement>>',
            'Academic Management': '<<AcademicManagement>>',
            'Exam Management': '<<ExamManagement>>',
            'Proctoring System': '<<Proctoring>>',
            'Communication System': '<<Communication>>',
            'System Configuration': '<<System>>'
        }
        
        for package_name, model_names in packages.items():
            output.append(f"package \"{package_name}\" {package_stereotypes[package_name]} {{\n\n")
            
            for model_name in model_names:
                if model_name not in self.models:
                    continue
                
                model_data = self.models[model_name]
                
                if model_name == 'User':
                    output.append(f"    class {model_name} <<extends AbstractUser>> {{\n")
                else:
                    output.append(f"    class {model_name} {{\n")
                
                for attr in model_data['attributes']:
                    output.append(f"        +{attr['name']}: {attr['type']}\n")
                
                for method in model_data['methods']:
                    output.append(f"        +{method['name']}: {method.get('return_type', 'void')}\n")
                
                output.append("    }\n\n")
            
            output.append("}\n\n")
        
        # Relationships (UML semantics)
        # - Composition (*--) when the part's lifecycle is owned by the whole
        # - Aggregation (o--) when it is a loose membership/containment
        # - Association (-->)
        relationships = [
            # User management
            "User \"1\" *-- \"1\" TeacherNotificationSettings : owns",

            # Academic
            "Subject \"1\" o-- \"*\" Group : organizes",
            "Subject \"1\" *-- \"*\" Question : defines",
            "Question \"1\" *-- \"*\" QuestionChoice : has",

            # Exams
            "Subject \"1\" o-- \"*\" Exam : offers",
            "Exam \"1\" *-- \"*\" ExamQuestion : contains",
            "Exam \"1\" o-- \"*\" StudentExam : attempts",
            "Exam \"1\" *-- \"*\" ExamEvent : logs",
            "ExamQuestion \"1\" o-- \"*\" StudentAnswer : answered by",
            "StudentExam \"1\" *-- \"*\" StudentAnswer : includes",

            # Proctoring
            "Exam \"1\" o-- \"*\" ProctorSession : monitors",
            "StudentExam \"0..1\" --> \"*\" ProctorSession : linked",
            "ProctorSession \"1\" *-- \"*\" ProctorSnapshot : captures",
            "ProctorSession \"1\" *-- \"1\" ProctorAudioStream : streams",

            # Communication
            "Group \"1\" *-- \"*\" GroupMessage : messages",
            "Message \"0..1\" --> \"*\" Message : replies_to",
            "Group \"1\" o-- \"*\" StudentJoinRequest : requests",

            # Ownership / participation (associations)
            "User \"1\" --> \"*\" Subject : teaches",
            "User \"*\" --> \"*\" Subject : enrolled_in",
            "User \"1\" --> \"*\" Group : manages",
            "User \"*\" --> \"*\" Group : member_of",
            "User \"1\" --> \"*\" Question : creates",
            "User \"1\" --> \"*\" Exam : creates",
            "User \"*\" --> \"*\" Exam : allowed_for",
            "User \"1\" --> \"*\" StudentExam : attempts",
            "User \"1\" --> \"*\" ExamEvent : triggers",
            "User \"1\" --> \"*\" Message : sends",
            "User \"1\" --> \"*\" Message : receives",
            "Exam \"1\" *-- \"*\" ExamNotification : notifies",
            "User \"1\" --> \"*\" GroupMessage : sends",
            "User \"1\" --> \"*\" StudentJoinRequest : submits",
            "User \"1\" --> \"*\" StudentJoinRequest : receives",
            "Question \"*\" --> \"*\" ExamQuestion : reused_in",
            "QuestionChoice \"0..1\" --> \"*\" StudentAnswer : selected",
        ]
        
        for rel in relationships:
            output.append(f"{rel}\n")
        
        output.append("\n@enduml")
        return ''.join(output)
    
    def generate_mermaid(self):
        """Generate Mermaid class diagram code."""
        output = []
        output.append("%%{init: {\n")
        output.append("  'theme':'base',\n")
        output.append("  'themeVariables': {\n")
        output.append("    'primaryColor':'#1976D2',\n")
        output.append("    'primaryTextColor':'#fff',\n")
        output.append("    'primaryBorderColor':'#1976D2',\n")
        output.append("    'lineColor':'#1976D2',\n")
        output.append("    'secondaryColor':'#E3F2FD',\n")
        output.append("    'background':'#ffffff'\n")
        output.append("  }\n")
        output.append("}}%%\n\n")
        output.append("classDiagram\n")
        
        for enum_name, enum_values in self.enums.items():
            output.append(f"    class {enum_name} {{\n")
            output.append("        <<enumeration>>\n")
            for value in enum_values:
                output.append(f"        {value}\n")
            output.append("    }\n\n")
        
        packages = {
            'User Management': ['User', 'TeacherNotificationSettings'],
            'Academic Management': ['Subject', 'Group', 'Question', 'QuestionChoice'],
            'Exam Management': ['Exam', 'ExamQuestion', 'StudentExam', 'StudentAnswer', 'ExamEvent', 'ExamNotification'],
            'Proctoring System': ['ProctorSession', 'ProctorSnapshot', 'ProctorAudioStream'],
            'Communication System': ['Message', 'GroupMessage', 'StudentJoinRequest'],
            'System Configuration': ['SystemSettings']
        }

        namespaces = {
            'User Management': 'UserManagement',
            'Academic Management': 'AcademicManagement',
            'Exam Management': 'ExamManagement',
            'Proctoring System': 'ProctoringSystem',
            'Communication System': 'CommunicationSystem',
            'System Configuration': 'SystemConfiguration',
        }
        
        for package_name, model_names in packages.items():
            ns = namespaces[package_name]
            output.append(f"    namespace {ns} {{\n")

            for model_name in model_names:
                if model_name not in self.models:
                    continue
                
                model_data = self.models[model_name]
                
                output.append(f"        class {model_name} {{\n")
                if model_name == 'User':
                    output.append("            <<extends AbstractUser>>\n")
                
                for attr in model_data['attributes']:
                    output.append(f"            +{attr['type']} {attr['name']}\n")
                
                for method in model_data['methods']:
                    # Mermaid method syntax:
                    # - visibility: + / - / # / ~ (prefix)
                    # - return type comes after a space
                    # - static methods end with `$`
                    return_type = method.get('return_type', 'void')
                    raw_name = method['name']
                    is_static = raw_name.strip().startswith('{static}')
                    name = raw_name.replace('{static}', '').strip()
                    static_suffix = '$' if is_static else ''
                    output.append(f"            +{name} {return_type}{static_suffix}\n")
                
                output.append("        }\n\n")

            output.append("    }\n\n")
        
        relationships = [
            # User management
            "    User \"1\" *-- \"1\" TeacherNotificationSettings : owns",

            # Academic
            "    Subject \"1\" o-- \"*\" Group : organizes",
            "    Subject \"1\" *-- \"*\" Question : defines",
            "    Question \"1\" *-- \"*\" QuestionChoice : has",

            # Exams
            "    Subject \"1\" o-- \"*\" Exam : offers",
            "    Exam \"1\" *-- \"*\" ExamQuestion : contains",
            "    Exam \"1\" o-- \"*\" StudentExam : attempts",
            "    Exam \"1\" *-- \"*\" ExamEvent : logs",
            "    ExamQuestion \"1\" o-- \"*\" StudentAnswer : answered by",
            "    StudentExam \"1\" *-- \"*\" StudentAnswer : includes",

            # Proctoring
            "    Exam \"1\" o-- \"*\" ProctorSession : monitors",
            "    StudentExam \"0..1\" --> \"*\" ProctorSession : linked",
            "    ProctorSession \"1\" *-- \"*\" ProctorSnapshot : captures",
            "    ProctorSession \"1\" *-- \"1\" ProctorAudioStream : streams",

            # Communication
            "    Group \"1\" *-- \"*\" GroupMessage : messages",
            "    Message \"0..1\" --> \"*\" Message : replies_to",
            "    Group \"1\" o-- \"*\" StudentJoinRequest : requests",

            # Ownership / participation (associations)
            "    User \"1\" --> \"*\" Subject : teaches",
            "    User \"*\" --> \"*\" Subject : enrolled_in",
            "    User \"1\" --> \"*\" Group : manages",
            "    User \"*\" --> \"*\" Group : member_of",
            "    User \"1\" --> \"*\" Question : creates",
            "    User \"1\" --> \"*\" Exam : creates",
            "    User \"*\" --> \"*\" Exam : allowed_for",
            "    User \"1\" --> \"*\" StudentExam : attempts",
            "    User \"1\" --> \"*\" ExamEvent : triggers",
            "    User \"1\" --> \"*\" Message : sends",
            "    User \"1\" --> \"*\" Message : receives",
            "    Exam \"1\" *-- \"*\" ExamNotification : notifies",
            "    User \"1\" --> \"*\" GroupMessage : sends",
            "    User \"1\" --> \"*\" StudentJoinRequest : submits",
            "    User \"1\" --> \"*\" StudentJoinRequest : receives",
            "    Question \"*\" --> \"*\" ExamQuestion : reused_in",
            "    QuestionChoice \"0..1\" --> \"*\" StudentAnswer : selected",
        ]
        
        for rel in relationships:
            output.append(f"{rel}\n")
        
        return ''.join(output)


class Command(BaseCommand):
    help = 'Generate class diagrams from Django models'

    def handle(self, *args, **options):
        analyzer = ModelAnalyzer()
        
        # Get all models
        core_models = apps.get_app_config('core').get_models()
        accounts_models = apps.get_app_config('accounts').get_models()
        all_models = list(core_models) + list(accounts_models)
        
        # Analyze each model
        for model in all_models:
            try:
                analyzer.analyze_model(model)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not analyze {model.__name__}: {e}"))
        
        # Generate diagrams
        diagram_dir = Path(__file__).parent.parent.parent.parent.parent / 'diagrams' / 'class diagram'
        diagram_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate PlantUML
        plantuml_code = analyzer.generate_plantuml()
        plantuml_file = diagram_dir / 'examination_system_class_diagram.puml'
        with open(plantuml_file, 'w', encoding='utf-8') as f:
            f.write(plantuml_code)
        self.stdout.write(self.style.SUCCESS(f'Generated PlantUML: {plantuml_file}'))
        
        # Generate Mermaid
        mermaid_code = analyzer.generate_mermaid()
        mermaid_file = diagram_dir / 'examination_system_class_diagram.mmd'
        with open(mermaid_file, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)
        self.stdout.write(self.style.SUCCESS(f'Generated Mermaid: {mermaid_file}'))
        
        self.stdout.write(self.style.SUCCESS('\nClass diagrams generated successfully!'))
