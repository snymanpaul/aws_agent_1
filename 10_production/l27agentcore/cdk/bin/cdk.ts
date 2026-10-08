#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { BaseStackProps } from '../lib/types';
import {
  DockerImageStack,
  AgentCoreStack
} from '../lib/stacks';

const app = new cdk.App();
const deploymentProps: BaseStackProps = {
  appName: "l27agentcore",
  // Use current CLI configuration for account/region
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION
  },
}
const dockerImageStack = new DockerImageStack(app, `l27agentcore-DockerImageStack`, deploymentProps);
const agentCoreStack = new AgentCoreStack(app, `l27agentcore-AgentCoreStack`, {
  ...deploymentProps,
  imageUri: dockerImageStack.imageUri
});
agentCoreStack.addDependency(dockerImageStack);

// Shared repo tag set (tools/aws_tags.py): owner + project select the paul-aws-agent-1 Resource Group.
const lessonTags: Record<string, string> = {
  owner: 'paul',
  project: 'aws_agent_1',
  lesson: 'L27',
  teardown: 'cdk destroy --all (10_production/l27agentcore/cdk)',
};
for (const [key, value] of Object.entries(lessonTags)) {
  cdk.Tags.of(app).add(key, value);
}
