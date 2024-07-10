# Semantic Conversational Search Workshop

This hands-on workshop aimed at developers and solution builders, introduces how to create a semantic search engine using [Amazon Opensearch Serverless](https://aws.amazon.com/opensearch-service/features/serverless/) and build a conversational search agent on top of it using Amazon Bedrock.
To illustrate this use case, we chose to build a movie search engine for a (B)VOD media platform as an example. However, the solution can easily be adapted to other industries like product search for e-commerce or property search for real estate.

The workshop is structured around five notebooks, including a notebook for cleaning up resources afterward. The first three notebooks cover data preparation, OpenSearch serverless collection creation, and embedding generation and loading into OpenSearch. The next two notebooks cover two different approaches to implementing a conversational search functionality.

The first approach is a Routing & Chaining approach, utilizing a Step Function and Lambda functions to implement the different capabilities of the chatbot. This method offers the following benefits:
- More deterministic than an agent approach
- Easier to optimize as you can break down the problem into different parts and optimize them separately
- Faster as it works with smaller and less complicated prompts that can run with smaller models like Anthropic Claude3 Haiku, for example.
The downside is the potential need to specify and manually handle many paths/cases.

The second approach uses an Agent, more specifically, Amazon Bedrock Agents. We define several tools at the agent's disposal to solve the question asked. The agent handles the planning and orchestration of tasks and tools to be called. The pros offered by an Agent include the flexibility to answer various questions and relative simplicity of implementation thanks to Amazon Bedrock. The potential downside is latency, as a lot of information and instructions need to be passed as part of the context, with multiple LLM calls performed to orchestrate the function callings.

## Pre-requisites

### Bedrock Access

To run through these notebooks, the AWS Account must have access to Amazon Bedrock. The notebooks are using Anthropic Claude 3 Haiku, Anthropic Claude 3 Sonnet and Cohere Embed English models. Before starting, ensure that you have the required model access enabled on Bedrock's Model Access page.

### Permissions

To run through these notebooks, you will need to ensure that your SageMaker execution role or your AWS CLI user has the necessary permissions/policies. 

See below a list of policies to attach to run the workshop: 
- IAMFullAccess, 
- AWSStepFunctionsFullAccess,
- AWSLambda_FullAccess, 
- SecretsManagerReadWrite
- AmazonBedrockFullAccess, 
- AmazonOpenSearchServiceFullAccess

As well as the following policy for OpenSearchServerless:

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "aoss:*",
                "Resource": "*"
            }
        ]
    }

Note that these policies are very permissive for the sake of simplicity in running the workshop, but they should be reviewed and minimized for production scenarios.

The workshop has been developed and tested in the following environments:

    Region: us-east-1
    Tested with Python 3.11.5 on Visual Studio with AWS CLI and AWS plugin configured
    Tested with SageMaker notebooks t3.large, conda_python3 kernel


## Part 0 - Data Preparation (Optional - if dataset is not provided)

This notebook is used to preprocess and clean the Movies Dataset used for the workshop. It utilizes a dataset available and to be downloaded from kaggle.com (under "CC0: Public Domain" license). Once transformed, the data is exported as two CSV files (full dataset and a smaller sample for the workshop).

## Part 1 - Open Search Serverless Collection creation

This notebook creates the OpenSearch Serverless collection and the associated Network, Encryption, and Data Access policies.

## Part 2 - OpenSearch index preparation

This notebook creates the OpenSearch (OS) index, generates vector embeddings from the previously created CSV file, and loads them into the OS index.

## Part 3 - Routing & Chaining implementation of the conversational search capability

This notebook starts by creating the required policies and roles, then creates the various Lambda functions, prompts, and test sets for each step (e.g., Routing, Semantic Search & Query Optimization, Filter-based Search, Sorting, etc.). It then creates the Step Function and performs a complete evaluation of the solution. Cleanup code is added at the end of this notebook to clean up related resources.

## Part 4 - Amazon Bedrock Agent implementation of the conversational search capability

This notebook starts with a short overview of the Agent concepts and proceeds to create the Lambda functions and policies/roles required for the execution of the Lambda functions by the Bedrock agent. It then creates the Lambda functions that are mapped to the "tools" we defined as part of the agent. It then goes into creating the agent, highlighting all the various prompts involved with the execution of the agents for your understanding. Finally, it creates the schema and the tools that will be added to the agent and goes into invoking and evaluating our overall solution. The notebook includes code at the end to clean up the Agent/Tools/Lambda resources.

## Part 5 - OpenSearch serverless deletion

This notebook provides the code to delete your OpenSearch Serverless collection and associated policies/roles.

