export { AcmisClient, type ClientOptions, type RequestOptions } from "./core/client"
export { ApiError, TransportError, type ApiErrorPayload } from "./core/errors"
export {
  attempt,
  describe,
  dataOr,
  firstProblem,
  type Outcome,
  type Problem,
  type ProblemKind,
} from "./core/outcome"
export { api, type Api, type PageQuery } from "./resources"
export * from "./types"
