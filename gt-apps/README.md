# gt-apps
An attempt to create a Operator that creates and manages CRD: GTApp. This is an example for Composite controller of Metacontroller.

This GTApp parent resource will create Child resources:
- Argo Rollout
- Keda's scaled object
- Services
- Argocd Application
- Istio Gateways
- Istio Virtualservices

