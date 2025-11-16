AWSTemplateFormatVersion: '2010-09-09'
Description: 'Complete CI/CD Pipeline: CodeCommit -> CodePipeline -> CodeDeploy with Validation and Auto-Rollback'

Parameters:
  ProjectName:
    Type: String
    Default: binary-calc
    Description: Project name (lowercase, no spaces)
    AllowedPattern: ^[a-z0-9-]+$

Resources:
  # ============================================
  # CODECOMMIT REPOSITORY
  # ============================================
  CodeRepository:
    Type: AWS::CodeCommit::Repository
    Properties:
      RepositoryName: !Sub '${ProjectName}-repo'
      RepositoryDescription: Binary Calculator Application

  # ============================================
  # S3 BUCKETS (Auto-generated names)
  # ============================================
  PipelineArtifactBucket:
    Type: AWS::S3::Bucket
    Properties:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  # ============================================
  # SNS TOPIC
  # ============================================
  NotificationTopic:
    Type: AWS::SNS::Topic
    Properties:
      DisplayName: Deployment Notifications

  NotificationTopicPolicy:
    Type: AWS::SNS::TopicPolicy
    Properties:
      Topics:
        - !Ref NotificationTopic
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service:
                - cloudwatch.amazonaws.com
                - codedeploy.amazonaws.com
            Action: SNS:Publish
            Resource: !Ref NotificationTopic

  # ============================================
  # IAM ROLES
  # ============================================
  LambdaRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

  ValidationRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: ValidationPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - codedeploy:PutLifecycleEventHookExecutionStatus
                  - lambda:InvokeFunction
                  - cloudwatch:PutMetricData
                Resource: '*'

  CodeBuildRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: codebuild.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: CodeBuildPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: '*'
              - Effect: Allow
                Action:
                  - s3:GetObject
                  - s3:PutObject
                Resource: !Sub '${PipelineArtifactBucket.Arn}/*'
              - Effect: Allow
                Action:
                  - lambda:UpdateFunctionCode
                  - lambda:GetFunction
                  - lambda:PublishVersion
                  - lambda:GetAlias
                Resource: !Sub '${CalculatorFunction.Arn}*'

  CodePipelineRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: codepipeline.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: PipelinePolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - s3:GetObject
                  - s3:PutObject
                Resource: !Sub '${PipelineArtifactBucket.Arn}/*'
              - Effect: Allow
                Action:
                  - codecommit:GetBranch
                  - codecommit:GetCommit
                  - codecommit:UploadArchive
                  - codecommit:GetUploadArchiveStatus
                Resource: !GetAtt CodeRepository.Arn
              - Effect: Allow
                Action:
                  - codebuild:BatchGetBuilds
                  - codebuild:StartBuild
                Resource: !GetAtt BuildProject.Arn
              - Effect: Allow
                Action:
                  - codedeploy:CreateDeployment
                  - codedeploy:GetApplication
                  - codedeploy:GetApplicationRevision
                  - codedeploy:GetDeployment
                  - codedeploy:GetDeploymentConfig
                  - codedeploy:RegisterApplicationRevision
                Resource: '*'

  CodeDeployRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: codedeploy.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSCodeDeployRoleForLambda

  EventBridgeRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: StartPipeline
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: codepipeline:StartPipelineExecution
                Resource: !Sub 'arn:aws:codepipeline:${AWS::Region}:${AWS::AccountId}:${Pipeline}'

  # ============================================
  # LAMBDA FUNCTIONS
  # ============================================
  CalculatorFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub '${ProjectName}-calculator'
      Runtime: python3.11
      Handler: index.handler
      Role: !GetAtt LambdaRole.Arn
      Code:
        ZipFile: |
          def handler(event, context):
              """Binary Calculator - Add two binary numbers"""
              try:
                  bin1 = event.get('binary1', '0')
                  bin2 = event.get('binary2', '0')

                  # Convert binary to decimal
                  num1 = int(bin1, 2)
                  num2 = int(bin2, 2)

                  # Add
                  result = num1 + num2

                  # Convert back to binary
                  result_binary = bin(result)[2:]

                  return {
                      'statusCode': 200,
                      'body': {
                          'input1': bin1,
                          'input2': bin2,
                          'result': result_binary,
                          'decimal': result
                      }
                  }
              except Exception as e:
                  return {
                      'statusCode': 400,
                      'body': {'error': str(e)}
                  }
      Timeout: 10

  CalculatorVersion:
    Type: AWS::Lambda::Version
    Properties:
      FunctionName: !Ref CalculatorFunction

  CalculatorAlias:
    Type: AWS::Lambda::Alias
    Properties:
      FunctionName: !Ref CalculatorFunction
      FunctionVersion: !GetAtt CalculatorVersion.Version
      Name: live

  ValidationFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub '${ProjectName}-validation'
      Runtime: python3.11
      Handler: index.handler
      Role: !GetAtt ValidationRole.Arn
      Code:
        ZipFile: |
          import json
          import boto3

          codedeploy = boto3.client('codedeploy')
          lambda_client = boto3.client('lambda')

          def handler(event, context):
              print(f"Validation started: {json.dumps(event)}")

              deployment_id = event['DeploymentId']
              lifecycle_id = event['LifecycleEventHookExecutionId']

              try:
                  # Test 1: Basic addition
                  result = lambda_client.invoke(
                      FunctionName='binary-calc-calculator:live',
                      Payload=json.dumps({
                          'binary1': '101',
                          'binary2': '11'
                      })
                  )

                  response = json.loads(result['Payload'].read())

                  if response['statusCode'] != 200:
                      raise Exception('Test failed: Invalid status code')

                  body = response['body']
                  if body['result'] != '1000':  # 5 + 3 = 8 = 1000 in binary
                      raise Exception(f"Test failed: Expected 1000, got {body['result']}")

                  print("✓ All tests passed")
                  status = 'Succeeded'

              except Exception as e:
                  print(f"✗ Validation failed: {str(e)}")
                  status = 'Failed'

              codedeploy.put_lifecycle_event_hook_execution_status(
                  deploymentId=deployment_id,
                  lifecycleEventHookExecutionId=lifecycle_id,
                  status=status
              )

              return {'statusCode': 200 if status == 'Succeeded' else 500}
      Timeout: 60

  # ============================================
  # CLOUDWATCH ALARMS
  # ============================================
  ErrorAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmName: !Sub '${ProjectName}-errors'
      MetricName: Errors
      Namespace: AWS/Lambda
      Statistic: Sum
      Period: 60
      EvaluationPeriods: 1
      Threshold: 1
      ComparisonOperator: GreaterThanThreshold
      Dimensions:
        - Name: FunctionName
          Value: !Ref CalculatorFunction
        - Name: Resource
          Value: !Sub '${CalculatorFunction}:live'
      AlarmActions:
        - !Ref NotificationTopic
      TreatMissingData: notBreaching

  ThrottleAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmName: !Sub '${ProjectName}-throttles'
      MetricName: Throttles
      Namespace: AWS/Lambda
      Statistic: Sum
      Period: 60
      EvaluationPeriods: 1
      Threshold: 3
      ComparisonOperator: GreaterThanThreshold
      Dimensions:
        - Name: FunctionName
          Value: !Ref CalculatorFunction
      AlarmActions:
        - !Ref NotificationTopic
      TreatMissingData: notBreaching

  # ============================================
  # CODEBUILD
  # ============================================
  BuildProject:
    Type: AWS::CodeBuild::Project
    Properties:
      Name: !Sub '${ProjectName}-build'
      ServiceRole: !GetAtt CodeBuildRole.Arn
      Artifacts:
        Type: CODEPIPELINE
      Environment:
        Type: LINUX_CONTAINER
        ComputeType: BUILD_GENERAL1_SMALL
        Image: aws/codebuild/standard:7.0
        EnvironmentVariables:
          - Name: FUNCTION_NAME
            Value: !Ref CalculatorFunction
      Source:
        Type: CODEPIPELINE
        BuildSpec: |
          version: 0.2
          phases:
            build:
              commands:
                - echo "Building deployment package..."
                - zip -j function.zip index.py

                - echo "Updating Lambda function..."
                - aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file fileb://function.zip
                - aws lambda wait function-updated --function-name $FUNCTION_NAME

                - echo "Publishing new version..."
                - NEW_VERSION=$(aws lambda publish-version --function-name $FUNCTION_NAME --query 'Version' --output text)
                - CURRENT_VERSION=$(aws lambda get-alias --function-name $FUNCTION_NAME --name live --query 'FunctionVersion' --output text)

                - echo "Creating AppSpec..."
                - |
                  cat > appspec.yaml <<EOF
                  version: 0.0
                  Resources:
                    - ${FUNCTION_NAME}:
                        Type: AWS::Lambda::Function
                        Properties:
                          Name: "${FUNCTION_NAME}"
                          Alias: "live"
                          CurrentVersion: "${CURRENT_VERSION}"
                          TargetVersion: "${NEW_VERSION}"
                  Hooks:
                    - BeforeAllowTraffic: "binary-calc-validation"
                  EOF
                - cat appspec.yaml
          artifacts:
            files:
              - appspec.yaml

  # ============================================
  # CODEDEPLOY
  # ============================================
  DeployApplication:
    Type: AWS::CodeDeploy::Application
    Properties:
      ApplicationName: !Sub '${ProjectName}-app'
      ComputePlatform: Lambda

  DeploymentGroup:
    Type: AWS::CodeDeploy::DeploymentGroup
    Properties:
      ApplicationName: !Ref DeployApplication
      DeploymentGroupName: !Sub '${ProjectName}-group'
      ServiceRoleArn: !GetAtt CodeDeployRole.Arn
      DeploymentConfigName: CodeDeployDefault.LambdaCanary10Percent5Minutes
      AutoRollbackConfiguration:
        Enabled: true
        Events:
          - DEPLOYMENT_FAILURE
          - DEPLOYMENT_STOP_ON_ALARM
      AlarmConfiguration:
        Enabled: true
        Alarms:
          - Name: !Ref ErrorAlarm
          - Name: !Ref ThrottleAlarm
      DeploymentStyle:
        DeploymentType: BLUE_GREEN
        DeploymentOption: WITH_TRAFFIC_CONTROL
      TriggerConfigurations:
        - TriggerName: DeploymentNotifications
          TriggerTargetArn: !Ref NotificationTopic
          TriggerEvents:
            - DeploymentStart
            - DeploymentSuccess
            - DeploymentFailure
            - DeploymentRollback

  # ============================================
  # CODEPIPELINE
  # ============================================
  Pipeline:
    Type: AWS::CodePipeline::Pipeline
    Properties:
      Name: !Sub '${ProjectName}-pipeline'
      RoleArn: !GetAtt CodePipelineRole.Arn
      ArtifactStore:
        Type: S3
        Location: !Ref PipelineArtifactBucket
      Stages:
        - Name: Source
          Actions:
            - Name: SourceAction
              ActionTypeId:
                Category: Source
                Owner: AWS
                Provider: CodeCommit
                Version: '1'
              Configuration:
                RepositoryName: !GetAtt CodeRepository.Name
                BranchName: main
                PollForSourceChanges: false
              OutputArtifacts:
                - Name: SourceOutput

        - Name: Build
          Actions:
            - Name: BuildAction
              ActionTypeId:
                Category: Build
                Owner: AWS
                Provider: CodeBuild
                Version: '1'
              Configuration:
                ProjectName: !Ref BuildProject
              InputArtifacts:
                - Name: SourceOutput
              OutputArtifacts:
                - Name: BuildOutput

        - Name: Deploy
          Actions:
            - Name: DeployAction
              ActionTypeId:
                Category: Deploy
                Owner: AWS
                Provider: CodeDeploy
                Version: '1'
              Configuration:
                ApplicationName: !Ref DeployApplication
                DeploymentGroupName: !Ref DeploymentGroup
              InputArtifacts:
                - Name: BuildOutput

  # ============================================
  # EVENTBRIDGE TRIGGER
  # ============================================
  PipelineTrigger:
    Type: AWS::Events::Rule
    Properties:
      EventPattern:
        source:
          - aws.codecommit
        detail-type:
          - CodeCommit Repository State Change
        detail:
          event:
            - referenceCreated
            - referenceUpdated
          referenceType:
            - branch
          referenceName:
            - main
        resources:
          - !GetAtt CodeRepository.Arn
      State: ENABLED
      Targets:
        - Arn: !Sub 'arn:aws:codepipeline:${AWS::Region}:${AWS::AccountId}:${Pipeline}'
          RoleArn: !GetAtt EventBridgeRole.Arn
          Id: PipelineTarget

# ============================================
# OUTPUTS
# ============================================
Outputs:
  RepositoryCloneUrl:
    Value: !GetAtt CodeRepository.CloneUrlHttp
    Description: Git clone URL

  PipelineUrl:
    Value: !Sub 'https://console.aws.amazon.com/codesuite/codepipeline/pipelines/${Pipeline}/view?region=${AWS::Region}'
    Description: Pipeline console URL

  FunctionName:
    Value: !Ref CalculatorFunction
    Description: Lambda function name

  SNSTopicArn:
    Value: !Ref NotificationTopic
    Description: SNS topic for notifications