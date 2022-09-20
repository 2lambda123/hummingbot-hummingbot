/* eslint-disable no-inner-declarations */
/* eslint-disable @typescript-eslint/ban-types */
import { Router, Request, Response } from 'express';
import { asyncHandler } from '../services/error-handler';
import { price } from './vault.controllers';
import { PriceRequest, PriceResponse } from './vault.requests';
import { validatePriceRequest } from './vault.validators';
export namespace VaultRoutes {
  export const router = Router();

  router.post(
    '/price',
    asyncHandler(
      async (
        req: Request<{}, {}, PriceRequest>,
        res: Response<PriceResponse | string, {}>
      ) => {
        validatePriceRequest(req.body);
        res.status(200).json(await price(req.body));
      }
    )
  );

  // router.post(
  //   '/trade',
  //   asyncHandler(
  //     async (
  //       req: Request<{}, {}, TradeRequest>,
  //       res: Response<TradeResponse | string, {}>
  //     ) => {
  //       validateTradeRequest(req.body);
  //       res.status(200).json(await trade(req.body));
  //     }
  //   )
  // );

  // router.post(
  //   '/estimateGas',
  //   asyncHandler(
  //     async (
  //       req: Request<{}, {}, NetworkSelectionRequest>,
  //       res: Response<EstimateGasResponse | string, {}>
  //     ) => {
  //       validateEstimateGasRequest(req.body);
  //       res.status(200).json(await estimateGas(req.body));
  //     }
  //   )
  // );
}
